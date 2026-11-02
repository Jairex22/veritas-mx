from apps.core.permissions import has_cap, register_file_access_hook


@register_file_access_hook
def label_outputs(user, stored_file):
    from .models import PrintJob

    jobs = PrintJob.objects.filter(output_pdf=stored_file) | PrintJob.objects.filter(output_zpl=stored_file)
    return any(j.user_id == user.pk or has_cap(user, "labels.reprint") for j in jobs)
