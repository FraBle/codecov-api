from rest_framework import serializers

from codecov_auth.models import Owner
from core.models import Commit, Repository


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = (
            "avatar_url",
            "service",
            "username",
            "name",
            "ownerid",
        )
        read_only_fields = fields


class RepositorySerializer(serializers.ModelSerializer):
    is_private = serializers.BooleanField(source="private")

    class Meta:
        model = Repository
        fields = ("name", "is_private", "active", "language", "yaml")
        read_only_fields = fields


class CommitSerializer(serializers.ModelSerializer):
    author = OwnerSerializer(read_only=True)
    repository = RepositorySerializer(read_only=True)

    class Meta:
        model = Commit
        read_only_fields = (
            "message",
            "timestamp",
            "ci_passed",
            "state",
            "repository",
            "author",
        )
        fields = read_only_fields + (
            "commitid",
            "parent_commit_id",
            "pullid",
            "branch",
        )