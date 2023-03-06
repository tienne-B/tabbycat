import logging
from subprocess import PIPE, Popen

from channels.consumer import SyncConsumer

from .models import Client
from .utils import get_postgres_url

logger = logging.getLogger(__name__)


class PortalQueueConsumer(SyncConsumer):

    def create_schema(self, event):
        logger.info("Creating new schema: %s" % (event['client'],))
        client = Client.objects.get(id=event.get('client'))
        client.create_schema()


class DatabaseBackupConsumer(SyncConsumer):

    def create_backup(self, event):
        logger.info("Creating backup: %s" % (event['uri'],))
        pg_process = Popen(['pg_dump', get_postgres_url(), '-n', '"'+event['schema_name']+'"', '-O', '-x', '-Fc'], stdout=PIPE)
        s3_process = Popen(['aws', 's3', 'cp', '-', event['uri']], stdin=pg_process.stdout, stdout=PIPE)
        pg_process.stdout.close()
        output, errors = s3_process.communicate()
        logger.info("Backup created")

    def restore_backup(self, event):
        logger.info("Restoring from backup: %s" % (event['uri'],))
        s3_process = Popen(['aws', 's3', 'cp', event['uri'], '-'], stdout=PIPE)
        pg_process = Popen(['pg_restore', '-d', get_postgres_url(),
            '-c', '--if-exists', '-n', '"'+event['schema_name']+'"', '-O', '-x'], stdin=s3_process.stdout, stdout=PIPE)
        s3_process.stdout.close()
        output, errors = pg_process.communicate()
