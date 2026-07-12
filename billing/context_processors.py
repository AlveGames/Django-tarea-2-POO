def notifications_processor(request):
    if request.user.is_authenticated:
        from .views import get_notifications, get_unread_notifications_count
        notifications = get_notifications(request.user)
        return {
            'notifications': notifications,
            'notifications_count': get_unread_notifications_count(request.user, request),
        }
    return {'notifications': [], 'notifications_count': 0}
