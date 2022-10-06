from rest_framework import serializers

from .models import Adjudicator, Institution, Speaker, SpeakerCategory, Team


class AdjudicatorSerializer(serializers.ModelSerializer):
    institution = serializers.SlugRelatedField(
        allow_null=True,
        queryset=Institution.objects.all(),
        slug_field='external_url',
    )

    institution_conflicts = serializers.SerializerMethodField(default=[])
    team_conflicts = serializers.SerializerMethodField(default=[])
    adjudicator_conflicts = serializers.SerializerMethodField(default=[])

    class Meta:
        model = Adjudicator
        fields = ('name', 'gender', 'email', 'institution', 'independent',
            'institution_conflicts', 'team_conflicts', 'adjudicator_conflicts')

    def get_institution_conflicts(self, obj):
        return []

    def get_team_conflicts(self, obj):
        return []

    def get_adjudicator_conflicts(self, obj):
        return []


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

    break_categories = serializers.SerializerMethodField(default=[])
    institution_conflicts = serializers.SerializerMethodField(default=[])

    class Meta:
        model = Team
        fields = ('reference', 'short_reference', 'use_institution_prefix',
            'institution', 'speakers', 'break_categories', 'institution_conflicts')

    def get_break_categories(self, obj):
        return []

    def get_institution_conflicts(self, obj):
        return []
