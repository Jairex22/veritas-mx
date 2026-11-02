from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.core.models import Area, Shift, StoredFile


class Announcement(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    RANK = {"normal": 1, "high": 2, "critical": 3}

    title = models.CharField("título", max_length=200)
    body = models.TextField("mensaje")
    priority = models.CharField("prioridad", max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    priority_rank = models.PositiveSmallIntegerField(default=1)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="announcements")
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)
    valid_from = models.DateTimeField("vigente desde", default=timezone.now)
    valid_until = models.DateTimeField("vigente hasta", null=True, blank=True)
    require_ack = models.BooleanField("requiere confirmación de lectura", default=False)
    areas = models.ManyToManyField(Area, blank=True, verbose_name="áreas")
    shifts = models.ManyToManyField(Shift, blank=True, verbose_name="turnos")
    groups = models.ManyToManyField(Group, blank=True, verbose_name="grupos")
    roles = models.JSONField(default=list, blank=True)
    attachments = models.ManyToManyField(StoredFile, blank=True)
    published = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-priority_rank", "-created"]

    def save(self, *args, **kwargs):
        self.priority_rank = self.RANK.get(self.priority, 1)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        now = timezone.now()
        return self.published and self.valid_from <= now and (self.valid_until is None or self.valid_until > now)


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(default=timezone.now)
    ack_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("announcement", "user")]


class Comment(models.Model):
    class Kind(models.TextChoices):
        COMMENT = "comment", "Comentario"
        QUESTION = "question", "Duda"
        INCIDENT = "incident", "Incidencia"

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey("content_type", "object_id")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.COMMENT)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    attachments = models.ManyToManyField(StoredFile, blank=True)

    class Meta:
        ordering = ["created"]
        indexes = [models.Index(fields=["content_type", "object_id"])]


class Conversation(models.Model):
    subject = models.CharField("asunto", max_length=200)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="conversations")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-updated"]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created"]


class ConversationRead(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="read_marks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_read = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("conversation", "user")]
