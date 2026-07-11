def cart(request):
    items = request.session.get('cart', {})
    count = sum(item.get('quantity', 0) for item in items.values())
    return {'cart_items_count': count}
