import logging

from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Subquery, OuterRef
from rest_framework import filters
from rest_framework import viewsets, mixins

from internal_api.mixins import RepoPropertyMixin
from codecov_auth.authentication.repo_auth import RepositoryLegacyTokenAuthentication
from core.models import Pull, Commit
from .permissions import PullUpdatePermission
from .serializers import PullSerializer
from services.task import TaskService

log = logging.getLogger(__name__)


class PullViewSet(
    RepoPropertyMixin,
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
):
    serializer_class = PullSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["state"]
    ordering_fields = ("pullid",)
    authentication_classes = [RepositoryLegacyTokenAuthentication]
    permission_classes = [PullUpdatePermission]

    def get_object(self):
        pullid = self.kwargs.get("pk")
        return get_object_or_404(self.get_queryset(), pullid=pullid)

    def get_queryset(self):
        return self.repo.pull_requests.annotate(
            ci_passed=Subquery(
                Commit.objects.filter(
                    commitid=OuterRef("head"), repository=OuterRef("repository")
                ).values("ci_passed")[:1]
            ),
        )
    
    def perform_update(self, serializer):
        result = super().perform_update(serializer)
        TaskService().pulls_sync(repoid=self.repo.repoid, pullid=self.kwargs.get("pk"))
        return result