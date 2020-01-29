from rest_framework import serializers

from core.models import Branch, Commit
from internal_api.owner.serializers import OwnerSerializer


class BranchCommitSerializer(serializers.ModelSerializer):
    author = OwnerSerializer()
    totals = serializers.JSONField()
    updatestamp = serializers.DateTimeField()

    class Meta:
        model = Commit
        fields = ('author', 'totals', 'updatestamp')


class BranchSerializer(serializers.ModelSerializer):
    name = serializers.CharField()
    head = BranchCommitSerializer()
    updatestamp = serializers.DateTimeField()

    class Meta:
        model = Branch
        fields = ('name', 'head', 'updatestamp')