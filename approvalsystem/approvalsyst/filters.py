import django_filters
from .models import PurchaseRequest

class PurchaseRequestFilter(django_filters.FilterSet):
    class Meta:
        model = PurchaseRequest
        fields = {
            'status': ['exact'],
            'created_by': ['exact'],
            'last_approved_by': ['exact'],
            # DO NOT include required_approval_levels
        }
