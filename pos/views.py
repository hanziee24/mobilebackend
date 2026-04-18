from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Count
from django.db import transaction
from decimal import Decimal
import random, string

from .models import Category, Product, Sale, SaleItem
from .serializers import CategorySerializer, ProductSerializer, SaleSerializer


def generate_receipt():
    ts = timezone.now().strftime('%Y%m%d%H%M%S')
    rand = ''.join(random.choices(string.digits, k=4))
    return f"RCP-{ts}-{rand}"


def is_admin_or_cashier(user):
    return user.user_type in ('ADMIN', 'CASHIER')


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    queryset = Category.objects.all()


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True)
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        if category:
            qs = qs.filter(category_id=category)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @action(detail=False, methods=['get'])
    def all_products(self, request):
        """Admin: get all products including inactive"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        products = Product.objects.all()
        return Response(ProductSerializer(products, many=True).data)

    @action(detail=False, methods=['get'])
    def by_barcode(self, request):
        """Lookup product by barcode"""
        code = request.query_params.get('code')
        if not code:
            return Response({'error': 'Barcode is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(barcode=code, is_active=True)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(ProductSerializer(product).data)

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        """Admin: quick restock a product"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        try:
            qty = int(request.data.get('quantity', 0))
        except (TypeError, ValueError):
            qty = 0

        if qty <= 0:
            return Response({'error': 'Quantity must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

        product = self.get_object()
        product.stock += qty
        product.save()

        return Response(ProductSerializer(product).data)


class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'ADMIN':
            return Sale.objects.all().order_by('-created_at')
        return Sale.objects.filter(cashier=user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def checkout(self, request):
        """Process a sale"""
        if not is_admin_or_cashier(request.user):
            return Response({'error': 'Cashier or Admin only'}, status=status.HTTP_403_FORBIDDEN)

        items_data = request.data.get('items', [])
        payment_method = request.data.get('payment_method', 'CASH')
        discount = Decimal(str(request.data.get('discount', '0')))
        amount_tendered = Decimal(str(request.data.get('amount_tendered', '0')))

        if not items_data:
            return Response({'error': 'No items provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate stock and calculate subtotal
        subtotal = Decimal('0')
        validated = []
        for item in items_data:
            try:
                product = Product.objects.get(id=item['product_id'], is_active=True)
            except Product.DoesNotExist:
                return Response({'error': f"Product {item['product_id']} not found"}, status=status.HTTP_400_BAD_REQUEST)

            qty = int(item['quantity'])
            if product.stock < qty:
                return Response({'error': f"Insufficient stock for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)

            item_subtotal = product.price * qty
            subtotal += item_subtotal
            validated.append({'product': product, 'quantity': qty, 'subtotal': item_subtotal})

        total = subtotal - discount
        change = amount_tendered - total if payment_method == 'CASH' else Decimal('0')

        # Create sale
        sale = Sale.objects.create(
            receipt_number=generate_receipt(),
            cashier=request.user,
            payment_method=payment_method,
            subtotal=subtotal,
            discount=discount,
            total=total,
            amount_tendered=amount_tendered,
            change=change,
        )

        # Create sale items and deduct stock
        for v in validated:
            SaleItem.objects.create(
                sale=sale,
                product=v['product'],
                product_name=v['product'].name,
                price=v['product'].price,
                quantity=v['quantity'],
                subtotal=v['subtotal'],
            )
            v['product'].stock -= v['quantity']
            v['product'].save()

        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def report(self, request):
        """Sales report — daily/weekly/monthly"""
        if not is_admin_or_cashier(request.user):
            return Response({'error': 'Admin or Cashier only'}, status=status.HTTP_403_FORBIDDEN)

        period = request.query_params.get('period', 'daily')
        now = timezone.now()

        if period == 'daily':
            sales = Sale.objects.filter(created_at__date=now.date())
        elif period == 'weekly':
            start = now - timezone.timedelta(days=7)
            sales = Sale.objects.filter(created_at__gte=start)
        else:
            sales = Sale.objects.filter(created_at__year=now.year, created_at__month=now.month)

        # Cashier only sees their own sales, admin sees all
        if request.user.user_type == 'CASHIER':
            sales = sales.filter(cashier=request.user)

        completed_sales = sales.filter(status='COMPLETED')
        total_sales = completed_sales.aggregate(total=Sum('total'))['total'] or 0
        total_transactions = completed_sales.count()

        top_products = (
            SaleItem.objects.filter(sale__in=completed_sales)
            .values('product_name')
            .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
            .order_by('-qty')[:5]
        )

        return Response({
            'period': period,
            'total_sales': str(total_sales),
            'total_transactions': total_transactions,
            'top_products': list(top_products),
            'sales': SaleSerializer(sales.order_by('-created_at')[:50], many=True).data,
        })

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Admin: void a sale and restock items"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        sale = self.get_object()
        if sale.status != 'COMPLETED':
            return Response({'error': 'Sale already voided or refunded'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for item in sale.items.all():
                if item.product:
                    item.product.stock += item.quantity
                    item.product.save()
            sale.status = 'VOIDED'
            sale.voided_at = timezone.now()
            sale.save()

        return Response(SaleSerializer(sale).data)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Admin: refund a sale and restock items"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        sale = self.get_object()
        if sale.status != 'COMPLETED':
            return Response({'error': 'Sale already voided or refunded'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for item in sale.items.all():
                if item.product:
                    item.product.stock += item.quantity
                    item.product.save()
            sale.status = 'REFUNDED'
            sale.refunded_at = timezone.now()
            sale.save()

        return Response(SaleSerializer(sale).data)
