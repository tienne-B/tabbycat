import json
import random
from dataclasses import asdict
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from channels.consumer import SyncConsumer
from django.conf import settings
from django.core import mail
from django.template import Context, Template
from html2text import html2text

from draw.models import Debate
from participants.models import Person
from portal.utils import using_tenant_schema
from tournaments.models import Round, Tournament

from .models import BulkNotification, SentMessage
from .utils import (AdjudicatorAssignmentEmailGenerator, BallotsEmailGenerator, MotionReleaseEmailGenerator,
                    NotificationContextGenerator, RandomizedUrlEmailGenerator, StandingsEmailGenerator,
                    TeamDrawEmailGenerator, TeamSpeakerEmailGenerator)


class NotificationQueueConsumer(SyncConsumer):

    NOTIFICATION_GENERATORS: Dict[BulkNotification.EventType, Type[NotificationContextGenerator]] = {
        BulkNotification.EventType.ADJ_DRAW: AdjudicatorAssignmentEmailGenerator,
        BulkNotification.EventType.URL: RandomizedUrlEmailGenerator,
        BulkNotification.EventType.BALLOTS_CONFIRMED: BallotsEmailGenerator,
        BulkNotification.EventType.POINTS: StandingsEmailGenerator,
        BulkNotification.EventType.MOTIONS: MotionReleaseEmailGenerator,
        BulkNotification.EventType.TEAM_REG: TeamSpeakerEmailGenerator,
        BulkNotification.EventType.TEAM_DRAW: TeamDrawEmailGenerator,
        BulkNotification.EventType.CUSTOM: NotificationContextGenerator,
    }

    @staticmethod
    def _send(messages: List[mail.EmailMultiAlternatives], records: List[SentMessage]) -> None:
        mail.get_connection().send_messages(messages)
        SentMessage.objects.bulk_create(records)

    def _get_from_fields(self, t: Tournament) -> Tuple[str, Optional[List[str]]]:
        from_email = formataddr((t.short_name, self.tenant + "@" + settings.EMAIL_DOMAIN))
        if t.pref('reply_to_address'):
            return from_email, [formataddr((t.pref('reply_to_name'), t.pref('reply_to_address')))]
        return from_email, None  # Shouldn't have array of None

    @using_tenant_schema
    def email(self, event: Dict[str, Union[str, BulkNotification.EventType, List[int], Dict[str, Any]]]) -> None:
        self.tenant = event['tenant']
        # Get database objects
        if 'debate_id' in event['extra']:
            debate = Debate.objects.select_related('round__tournament').get(pk=event['extra'].pop('debate_id'))
            event['extra']['debate'] = debate
            round = event['extra']['debate'].round
            t = round.tournament
        elif 'round_id' in event['extra']:
            round = Round.objects.select_related('tournament').get(pk=event['extra'].pop('round_id'))
            event['extra']['round'] = round
            t = round.tournament
        else:
            round = None
            t = Tournament.objects.get(pk=event['extra'].pop('tournament_id'))
            event['extra']['tournament'] = t

        from_email, reply_to = self._get_from_fields(t)
        notification_type = event['message']

        subject = Template(event['subject'])
        html_body = Template(event['body'])

        recipients = Person.objects.filter(pk__in=event['send_to'] or [], email__isnull=False).exclude(email='')
        contexts = self.NOTIFICATION_GENERATORS[notification_type].generate(to=recipients, **event['extra'])

        # Prepare messages

        # Ballot receipts are grouped by round in the same BulkNotification
        creation_kwargs = {
            'round': round,
            'tournament': t,
            'subject_template': event['subject'],
            'body_template': event['body'],
        }
        if notification_type is BulkNotification.EventType.BALLOTS_CONFIRMED:
            bulk_notification, c = BulkNotification.objects.get_or_create(
                event=BulkNotification.EventType.BALLOTS_CONFIRMED, **creation_kwargs)
        else:
            bulk_notification = BulkNotification.objects.create(event=notification_type, **creation_kwargs)

        messages = []
        records = []
        for instance, recipient in contexts:
            data = asdict(instance)
            data['USER'] = recipient.name

            hook_id = str(bulk_notification.id) + "-" + str(recipient.id) + "-" + str(random.randint(1000, 9999))
            context = Context(data)
            body = html_body.render(context)
            email = mail.EmailMultiAlternatives(
                subject=subject.render(context), body=html2text(body),
                from_email=from_email, to=[formataddr((recipient.name, recipient.email))],
                reply_to=reply_to, headers={
                    'X-SMTPAPI': json.dumps({'unique_args': {'hook-id': hook_id}}),  # SendGrid-specific 'hook-id'
                    'X-HOOKID': hook_id,
                    'X-TCSITE': event['tenant'],
                },
            )
            email.attach_alternative(body, "text/html")
            messages.append(email)

            raw_message = email.message()
            records.append(
                SentMessage(recipient=recipient, email=recipient.email,
                            method=SentMessage.METHOD_TYPE_EMAIL,
                            context=data, message_id=raw_message['Message-ID'],
                            hook_id=hook_id, notification=bulk_notification))

        self._send(messages, records)

    @using_tenant_schema
    def email_custom(self, event):
        self.tenant = event['tenant']
        messages = []
        records = []

        t = Tournament.objects.get(id=event['tournament'])
        from_email, reply_to = self._get_from_fields(t)

        recipients = Person.objects.filter(pk__in=event['send_to'], email__isnull=False).exclude(email='')

        bulk_notification = BulkNotification.objects.create(tournament=t, subject_template=event['subject'], body_template=event['body'])
        for recipient in recipients:
            hook_id = str(bulk_notification.id) + "-" + str(recipient.pk) + "-" + str(random.randint(1000, 9999))
            email = mail.EmailMultiAlternatives(
                subject=event['subject'], body=html2text(event['body']),
                from_email=from_email, to=[formataddr((recipient.name, recipient.email))],
                reply_to=reply_to, headers={
                    'X-SMTPAPI': json.dumps({'unique_args': {'hook-id': hook_id}}),  # SendGrid-specific 'hook-id'
                    'X-HOOKID': hook_id,
                    'X-TCSITE': event['tenant'],
                },
            )
            email.attach_alternative(event['body'], "text/html")
            messages.append(email)

            raw_message = email.message()
            records.append(
                SentMessage(recipient=recipient, email=recipient.email,
                            method=SentMessage.METHOD_TYPE_EMAIL,
                            message_id=raw_message['Message-ID'], hook_id=hook_id,
                            notification=bulk_notification))

        self._send(messages, records)
