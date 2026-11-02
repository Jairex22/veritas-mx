from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.core.models import Area, Role, Shift

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(label="Roles destinatarios (vacío = todos)", choices=Role.choices, required=False,
                                      widget=forms.CheckboxSelectMultiple)
    areas = forms.ModelMultipleChoiceField(label="Áreas (vacío = todas)", queryset=Area.objects.filter(active=True), required=False,
                                           widget=forms.CheckboxSelectMultiple)
    shifts = forms.ModelMultipleChoiceField(label="Turnos (vacío = todos)", queryset=Shift.objects.filter(active=True), required=False,
                                            widget=forms.CheckboxSelectMultiple)
    groups = forms.ModelMultipleChoiceField(label="Grupos (vacío = todos)", queryset=Group.objects.all(), required=False,
                                            widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Announcement
        fields = ["title", "body", "priority", "valid_from", "valid_until", "require_ack", "areas", "shifts", "groups", "roles"]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "body": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("valid_from", "valid_until"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        data = super().clean()
        if data.get("valid_until") and data.get("valid_from") and data["valid_until"] <= data["valid_from"]:
            self.add_error("valid_until", "La vigencia final debe ser posterior al inicio.")
        return data


class ConversationForm(forms.Form):
    subject = forms.CharField(label="Asunto", max_length=200)
    participants = forms.ModelMultipleChoiceField(label="Participantes", queryset=get_user_model().objects.filter(is_active=True).order_by("username"),
                                                  widget=forms.SelectMultiple(attrs={"size": 8}))
    body = forms.CharField(label="Mensaje", widget=forms.Textarea(attrs={"rows": 4}))
