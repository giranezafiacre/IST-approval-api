from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# Create your models here.
class PurchaseRequest(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_by = models.ForeignKey(User, related_name='purchase_requests', on_delete=models.PROTECT)
    last_approved_by = models.ForeignKey(User, null=True, blank=True, related_name='approved_requests', on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # file uploads
    proforma = models.ForeignKey('Proforma', null=True, blank=True, on_delete=models.SET_NULL)
    purchase_order = models.FileField(upload_to='purchase_orders/', null=True, blank=True)
    receipt = models.FileField(upload_to='receipts/', null=True, blank=True)

    # optional: number of approval levels required - fallback to SETTINGS
    required_approval_levels = models.JSONField(default=list, blank=True)  # e.g. [1,2]

    def is_editable(self):
        return self.status == self.STATUS_PENDING

    def __str__(self):
        return f"{self.title} ({self.status})"


class RequestItem(models.Model):
    request = models.ForeignKey(PurchaseRequest, related_name='items', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def total(self):
        return self.qty * self.unit_price


class Approval(models.Model):
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    ACTION_CHOICES = [(APPROVED, 'Approved'), (REJECTED, 'Rejected')]

    purchase_request = models.ForeignKey(PurchaseRequest, related_name='approvals', on_delete=models.CASCADE)
    approver = models.ForeignKey(User, on_delete=models.PROTECT)
    level = models.PositiveSmallIntegerField()  # 1,2 etc
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('purchase_request', 'approver', 'level')  # prevents duplicate same-level approvals

class PurchaseOrder(models.Model):
    proforma = models.ForeignKey('Proforma', null=True, blank=True, on_delete=models.CASCADE)
    vendor_name = models.CharField(max_length=255)
    items = models.TextField(default='')  # could be JSON or plain text
    total_amount = models.DecimalField(max_digits=10, decimal_places=2,default=0.00)
    purchase_request = models.OneToOneField(PurchaseRequest, related_name='po', on_delete=models.CASCADE)
    generated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    generated_at = models.DateTimeField(auto_now_add=True)
    po_file = models.FileField(upload_to='purchase_orders/', null=True, blank=True)  # can be populated by generator
    reference = models.CharField(max_length=100, blank=True, null=True)

class Proforma(models.Model):
    file = models.FileField(upload_to='proformas/')
    vendor_name = models.CharField(max_length=255, blank=True, null=True)
    items = models.JSONField(blank=True, null=True)  # list of {name, qty, unit_price}
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)