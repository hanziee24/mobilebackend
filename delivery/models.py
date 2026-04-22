from django.db import models
from user.models import User

class DeliveryFeeConfig(models.Model):
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    per_kg_rate = models.DecimalField(max_digits=10, decimal_places=2, default=15)
    per_item_rate = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Fee Config: Base ₱{self.base_fee} | ₱{self.per_kg_rate}/kg | ₱{self.per_item_rate}/item'

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(id=1, defaults={
            'base_fee': 50, 'per_kg_rate': 15, 'per_item_rate': 10
        })
        return config


class Delivery(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PICKED_UP', 'Picked Up'),
        ('IN_TRANSIT', 'In Transit'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('FAILED', 'Failed Delivery'),
        ('CANCELLED', 'Cancelled'),
    )
    
    tracking_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_deliveries')
    rider = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rider_deliveries')
    
    # Sender info
    sender_name = models.CharField(max_length=200, blank=True, null=True)
    sender_contact = models.CharField(max_length=20, blank=True, null=True)
    
    # Receiver info
    receiver_name = models.CharField(max_length=200, blank=True, null=True)
    receiver_contact = models.CharField(max_length=20, blank=True, null=True)
    
    pickup_address = models.TextField()
    delivery_address = models.TextField()
    
    # Package handling
    is_fragile = models.BooleanField(default=False)
    package_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    package_length = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    package_width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    package_height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    package_photo = models.ImageField(upload_to='packages/', blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    
    # Time slot selection
    delivery_time_slot = models.CharField(max_length=20, choices=[
        ('MORNING', 'Morning (8AM-12PM)'),
        ('AFTERNOON', 'Afternoon (12PM-5PM)'),
        ('EVENING', 'Evening (5PM-8PM)'),
        ('ANYTIME', 'Anytime')
    ], default='ANYTIME', blank=True, null=True)
    scheduled_date = models.DateField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    progress = models.IntegerField(default=0)
    
    estimated_time = models.CharField(max_length=50, blank=True, null=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True, null=True)
    failure_reason = models.CharField(max_length=200, blank=True, null=True)
    delivery_attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    proof_of_delivery = models.ImageField(upload_to='proofs/', blank=True, null=True)
    
    # GCash payment details (set by customer)
    gcash_name = models.CharField(max_length=200, blank=True, null=True)
    gcash_number = models.CharField(max_length=20, blank=True, null=True)
    gcash_proof = models.ImageField(upload_to='gcash_proofs/', blank=True, null=True)

    # Payment info collected by cashier
    payment_method = models.CharField(max_length=20, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)

    is_approved = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.tracking_number

class DeliveryRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('CANCELLED', 'Cancelled'),
    )
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='delivery_requests')
    sender_name = models.CharField(max_length=200)
    sender_contact = models.CharField(max_length=20)
    sender_address = models.TextField()
    receiver_name = models.CharField(max_length=200)
    receiver_contact = models.CharField(max_length=20)
    receiver_address = models.TextField()
    item_type = models.CharField(max_length=200)
    weight = models.CharField(max_length=20)
    quantity = models.CharField(max_length=20)
    is_fragile = models.BooleanField(default=False)
    special_instructions = models.TextField(blank=True, null=True)
    preferred_payment_method = models.CharField(max_length=20, blank=True, null=True, default='CASH')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Request #{self.id} from {self.customer.username}'


class ChatMessage(models.Model):
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.message[:30]}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"

class Rating(models.Model):
    delivery = models.OneToOneField(Delivery, on_delete=models.CASCADE, related_name='rating')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_ratings')
    rider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_ratings')
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5 stars
    comment = models.TextField(blank=True, null=True)
    tip_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.username} rated {self.rider.username} - {self.rating} stars"
