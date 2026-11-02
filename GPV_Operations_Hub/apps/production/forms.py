from django import forms
from django.contrib.auth import get_user_model

from .fields import FIELDS
from .models import Dataset, WorkOrder


class PlanEditForm(forms.ModelForm):
    reason = forms.CharField(label="Motivo del cambio (obligatorio)", max_length=300, min_length=5)
    assigned_users = forms.ModelMultipleChoiceField(label="Operadores asignados", required=False,
                                                    queryset=get_user_model().objects.filter(is_active=True).order_by("username"),
                                                    widget=forms.SelectMultiple(attrs={"size": 6}))

    class Meta:
        model = WorkOrder
        fields = ["qty_planned", "priority", "due", "status", "responsible", "assigned_users"]
        widgets = {"due": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        self.fields["qty_planned"].min_value = 0

    def clean_qty_planned(self):
        v = self.cleaned_data.get("qty_planned")
        if v is not None and v < 0:
            raise forms.ValidationError("La meta no puede ser negativa.")
        return v


class DatasetForm(forms.ModelForm):
    key_fields = forms.MultipleChoiceField(label="Campos clave (identifican un registro)", required=False,
                                           choices=[(k, v[0]) for k, v in FIELDS.items()], widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Dataset
        fields = ["code", "name", "kind", "area", "description", "key_fields", "unit_default", "finished_station", "counts_as_production"]
