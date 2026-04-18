from django.core.management.base import BaseCommand
from delivery.models import Delivery
from payment.models import RiderWallet, WalletTransaction

class Command(BaseCommand):
    help = 'Backfill rider wallets with earnings from completed deliveries'

    def handle(self, *args, **options):
        delivered = Delivery.objects.filter(status='DELIVERED', rider__isnull=False)
        
        self.stdout.write(f'Found {delivered.count()} delivered orders')
        
        credited = 0
        for delivery in delivered:
            # Check if already credited
            if WalletTransaction.objects.filter(delivery=delivery).exists():
                continue
            
            wallet, created = RiderWallet.objects.get_or_create(rider=delivery.rider)
            
            balance_before = wallet.balance
            wallet.balance += delivery.delivery_fee
            wallet.total_earned += delivery.delivery_fee
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='EARNING',
                amount=delivery.delivery_fee,
                balance_before=balance_before,
                balance_after=wallet.balance,
                delivery=delivery,
                description=f'Delivery fee for {delivery.tracking_number} (backfilled)'
            )
            
            credited += 1
            self.stdout.write(f'Credited ₱{delivery.delivery_fee} to {delivery.rider.get_full_name()}')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully credited {credited} deliveries'))
