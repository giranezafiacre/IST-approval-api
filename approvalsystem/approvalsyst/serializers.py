from rest_framework import serializers
from .models import PurchaseRequest, RequestItem, Approval, Proforma, PurchaseOrder
from django.conf import settings
from rest_framework import serializers
from django.contrib.auth.models import User
import json


class RequestItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestItem
        fields = ('id', 'name', 'qty', 'unit_price', 'total')
        read_only_fields = ('total',)

class PurchaseRequestSerializer(serializers.ModelSerializer):
    items = RequestItemSerializer(many=True, required=False)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = ('id','title','description','amount','status','created_by','created_at','updated_at','proforma','purchase_order','receipt','items','required_approval_levels')
        read_only_fields = ('purchase_order','amount',)

    def create(self, validated_data):
        items_data = self.context['request'].data.get('items', [])
        if isinstance(items_data, str):
            try:
                items_data = json.loads(items_data)
            except json.JSONDecodeError:
                items_data = []

        user = self.context['request'].user
        validated_data['created_by'] = user
        validated_data.pop('items', None)

        # Calculate total amount from items
        total_amount = sum(item['qty'] * item['unit_price'] for item in items_data)
        validated_data['amount'] = total_amount
        print("items_data:", items_data)
        print("total_amount:", total_amount)

        if not validated_data.get('required_approval_levels'):
            validated_data['required_approval_levels'] = getattr(settings, 'REQUIRED_APPROVAL_LEVELS', [1,2])

        pr = PurchaseRequest.objects.create(**validated_data)
        for item in items_data:
            RequestItem.objects.create(request=pr, **item)
        return pr

    def update(self, instance, validated_data):
        # disallow updates if not pending
        if instance.status != PurchaseRequest.STATUS_PENDING:
            raise serializers.ValidationError("Only pending requests can be updated.")
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                RequestItem.objects.create(request=instance, **item)
        return instance

class ApprovalSerializer(serializers.ModelSerializer):
    approver = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = Approval
        fields = ('id','purchase_request','approver','level','action','comment','created_at')
        read_only_fields = ('approver','created_at')

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role']
    def get_role(self, obj):
        print("User groups:", obj.groups.all())
        if obj.groups.exists():
            return obj.groups.first().name.lower()   # example: "staff", "finance"
        return "staff"
    
class PurchaseOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = ['id', 'proforma', 'vendor_name', 'items', 'total_amount', 'generated_by', 'generated_at']
    items = serializers.JSONField()

class ProformaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proforma
        fields = ['id', 'file', 'vendor_name', 'items', 'total_amount', 'uploaded_at']
