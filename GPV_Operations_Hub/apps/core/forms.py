from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import Area, Profile, Role, Shift


class _ProfileFields(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=Role.choices)
    areas = forms.ModelMultipleChoiceField(label="Áreas", queryset=Area.objects.filter(active=True), required=False,
                                           widget=forms.CheckboxSelectMultiple)
    all_areas = forms.BooleanField(label="Acceso a todas las áreas", required=False)
    shift = forms.ModelChoiceField(label="Turno", queryset=Shift.objects.all(), required=False)
    employee_number = forms.CharField(label="Número de empleado", required=False, max_length=40)


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña temporal", widget=forms.PasswordInput)
    role = _ProfileFields.base_fields["role"]
    areas = _ProfileFields.base_fields["areas"]
    all_areas = _ProfileFields.base_fields["all_areas"]
    shift = _ProfileFields.base_fields["shift"]
    employee_number = _ProfileFields.base_fields["employee_number"]

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email"]
        labels = {"username": "Usuario", "first_name": "Nombre", "last_name": "Apellidos", "email": "Correo (solo referencia)"}

    def clean_password1(self):
        pwd = self.cleaned_data["password1"]
        validate_password(pwd)
        return pwd

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.set_password(self.cleaned_data["password1"])
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data["role"]
            profile.all_areas = self.cleaned_data["all_areas"]
            profile.shift = self.cleaned_data["shift"]
            profile.employee_number = self.cleaned_data["employee_number"]
            profile.must_change_password = True
            profile.save()
            profile.areas.set(self.cleaned_data["areas"])
        return user


class UserEditForm(forms.ModelForm):
    role = _ProfileFields.base_fields["role"]
    areas = _ProfileFields.base_fields["areas"]
    all_areas = _ProfileFields.base_fields["all_areas"]
    shift = _ProfileFields.base_fields["shift"]
    employee_number = _ProfileFields.base_fields["employee_number"]
    new_password = forms.CharField(label="Restablecer contraseña (opcional)", widget=forms.PasswordInput, required=False)

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email", "is_active"]
        labels = {"first_name": "Nombre", "last_name": "Apellidos", "email": "Correo (solo referencia)", "is_active": "Activo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p = self.instance.profile
        self.initial.update({"role": p.role, "areas": p.areas.all(), "all_areas": p.all_areas, "shift": p.shift,
                             "employee_number": p.employee_number})

    def clean_new_password(self):
        pwd = self.cleaned_data.get("new_password")
        if pwd:
            validate_password(pwd, self.instance)
        return pwd

    def save(self, commit=True):
        user = super().save()
        p = user.profile
        p.role = self.cleaned_data["role"]
        p.all_areas = self.cleaned_data["all_areas"]
        p.shift = self.cleaned_data["shift"]
        p.employee_number = self.cleaned_data["employee_number"]
        if self.cleaned_data.get("new_password"):
            user.set_password(self.cleaned_data["new_password"])
            user.save()
            p.must_change_password = True
        p.save()
        p.areas.set(self.cleaned_data["areas"])
        return user


class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["code", "name", "active"]


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ["code", "name", "start", "end", "active"]
        widgets = {"start": forms.TimeInput(attrs={"type": "time"}), "end": forms.TimeInput(attrs={"type": "time"})}
