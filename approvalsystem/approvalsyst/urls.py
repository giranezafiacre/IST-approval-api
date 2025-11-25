from rest_framework.routers import DefaultRouter
from .views import PurchaseRequestViewSet,me, UploadProformaView, FinancePurchaseRequestViewSet
from django.urls import path, include

router = DefaultRouter()
router.register(r'requests', PurchaseRequestViewSet, basename='purchase-request')
finance_router = DefaultRouter()
finance_router.register(r'requests', FinancePurchaseRequestViewSet, basename='finance-requests')

urlpatterns = [
    path('api/finance/', include(finance_router.urls)),
    path('api/proforma/upload/', UploadProformaView.as_view(), name='upload-proforma'),
    path('api/', include(router.urls)),
    path('api/users/me/', me, name='user-me')
]
