import requests
import json

def send_push_notification(push_token, title, body, data=None):
    """Send push notification using Expo Push Notification service"""
    if not push_token:
        return False
    
    message = {
        "to": push_token,
        "sound": "default",
        "title": title,
        "body": body,
        "data": data or {},
        "priority": "high",
    }
    
    try:
        response = requests.post(
            'https://exp.host/--/api/v2/push/send',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            data=json.dumps(message)
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send push notification: {e}")
        return False

def notify_rider_new_delivery(rider, delivery):
    """Notify rider about new delivery assignment"""
    if rider.push_token:
        send_push_notification(
            rider.push_token,
            "🚚 New Delivery Assigned",
            f"Pick up package {delivery.tracking_number} - ₱{delivery.delivery_fee}",
            {"type": "new_delivery", "delivery_id": delivery.id}
        )

def notify_customer_status_update(customer, delivery, status):
    """Notify customer about delivery status change"""
    if customer.push_token:
        status_messages = {
            'PICKED_UP': f"📦 Your package {delivery.tracking_number} has been picked up by the rider",
            'IN_TRANSIT': f"🚚 Your package {delivery.tracking_number} is on the way",
            'DELIVERED': f"✅ Your package {delivery.tracking_number} has been delivered",
            'FAILED': f"❌ Delivery attempt failed for {delivery.tracking_number}",
        }
        message = status_messages.get(status, f"Status updated: {status}")
        send_push_notification(
            customer.push_token,
            "Delivery Update",
            message,
            {"type": "status_update", "delivery_id": delivery.id, "status": status}
        )

def notify_rider_payment_received(rider, amount):
    """Notify rider about payment received"""
    if rider.push_token:
        send_push_notification(
            rider.push_token,
            "💰 Payment Received",
            f"You received ₱{amount} for completed delivery",
            {"type": "payment", "amount": str(amount)}
        )
