from rest_framework import serializers

from .models import Adjudicator, Institution, Speaker, SpeakerCategory, Team


class AdjudicatorSerializer(serializers.ModelSerializer):
    institution = serializers.SlugRelatedField(
        allow_null=True,
        queryset=Institution.objects.all(),
        slug_field='external_url',
    )

    institution_conflicts = serializers.HiddenField(default=[])
    team_conflicts = serializers.HiddenField(default=[])
    adjudicator_conflicts = serializers.HiddenField(default=[])

    class Meta:
        model = Adjudicator
        fields = ('name', 'gender', 'email', 'institution', 'independent')


class InstitutionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Institution
        fields = ('name', 'code')


class SpeakerSerializer(serializers.ModelSerializer):
    categories = serializers.SlugRelatedField(
        many=True,
        queryset=SpeakerCategory.objects.all(),
        slug_field='external_url',
    )

    class Meta:
        model = Speaker
        fields = ('name', 'gender', 'email', 'categories')


class TeamSerializer(serializers.ModelSerializer):
    speakers = SpeakerSerializer(many=True, source='speaker_set')
    institution = serializers.SlugRelatedField(
        allow_null=True,
        queryset=Institution.objects.all(),
        slug_field='external_url',
    )

    break_categories = serializers.HiddenField(default=[])
    institution_conflicts = serializers.HiddenField(default=[])

    class Meta:
        model = Team
        fields = ('reference', 'short_reference', 'use_institution_prefix',
            'institution', 'speakers', 'break_categories', 'institution_conflicts')

    def get_break_categories(self, obj):
        return []

    def get_institution_conflicts(self, obj):
        return []
