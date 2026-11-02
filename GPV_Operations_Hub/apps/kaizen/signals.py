from apps.core.permissions import can_access_area, register_file_access_hook


@register_file_access_hook
def kaizen_evidence(user, stored_file):
    return any(can_access_area(user, imp.area_id) for imp in stored_file.improvement_set.all())
