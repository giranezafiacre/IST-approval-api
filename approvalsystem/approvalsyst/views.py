from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404

from approvalsystem.approvalsyst.filters import PurchaseRequestFilter
from .models import PurchaseRequest, Approval, PurchaseOrder, Proforma
from .utils import extract_pdf_data
from .serializers import PurchaseRequestSerializer,UserSerializer, ProformaSerializer, PurchaseOrderSerializer
from rest_framework.views import APIView
from .permissions import IsOwnerOrReadOnly, IsApprover, IsStaff, IsFinance, user_has_role
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


class FinancePurchaseRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Finance team: can view approved requests only
    """
    serializer_class = PurchaseRequestSerializer
    permission_classes = [IsAuthenticated, IsFinance]

    def get_queryset(self):
        # Only approved requests
        return PurchaseRequest.objects.filter(status=PurchaseRequest.STATUS_APPROVED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)

class UploadProformaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file uploaded'}, status=400)

        proforma = Proforma.objects.create(file=file, created_by=request.user)

        # Extract key data
        data = extract_pdf_data(file)
        proforma.vendor_name = data.get('vendor')
        proforma.items = data.get('items')
        proforma.total_amount = data.get('total')
        proforma.save()
        
        purchase_request = PurchaseRequest.objects.create(
            title=f"Request from {request.user.username}",
            description=f"Generated from proforma {file.name}",
            created_by=request.user,
            status=PurchaseRequest.STATUS_PENDING,
            amount=proforma.total_amount,
            proforma=proforma.file 
        )
        # Create PO automatically
        po = PurchaseOrder.objects.create(
            purchase_request=purchase_request,
            proforma=proforma,
            vendor_name=proforma.vendor_name,
            items=proforma.items,
            total_amount=proforma.total_amount
        )

        return Response({
            'proforma': ProformaSerializer(proforma).data,
            'purchase_order': PurchaseOrderSerializer(po).data
        })


class PurchaseRequestViewSet(viewsets.ModelViewSet):
    queryset = PurchaseRequest.objects.all().select_related('created_by','last_approved_by').prefetch_related('items','approvals')
    serializer_class = PurchaseRequestSerializer
    filterset_class = PurchaseRequestFilter
    filterset_fields = ['status', 'created_by', 'last_approved_by']

    def get_permissions(self):
        # apply basic permission: authenticated
        if self.action in ['create', 'update', 'partial_update', 'submit_receipt']:
            return [IsStaff(),]
        if self.action in ['approve', 'reject','list_pending','reviewed']:
            return [IsApprover(),]
        # finance can access via web UI endpoints -> check in front end and backend as needed
        return [IsOwnerOrReadOnly(),]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        # staff should only see their own requests unless other roles
        if user_has_role(user, 'staff'):
            return qs.filter(created_by=user)
        # approvers/finance see pending or all depending
        if user_has_role(user, 'approver'):
           return qs

        if user_has_role(user, 'finance'):
            return qs

        return qs.none()
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        is_staff_or_creator = (
            user_has_role(user, 'staff') or instance.created_by == user
        )
        if instance.status != instance.STATUS_PENDING:
            return Response(
                {"detail": f"Cannot update a request with status '{instance.status}'. Only PENDING requests are editable."},
                status=status.HTTP_400_BAD_REQUEST
            )
            return super().update(request, *args, **kwargs)
        with transaction.atomic():
            pr = self.get_queryset().select_for_update().get(pk=instance.pk)

            if pr.status != pr.STATUS_PENDING:
                return Response(
                    {"detail": f"Cannot update a request with status '{pr.status}'. Only PENDING requests are editable."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().update(request, *args, **kwargs)
        
    @action(detail=True, methods=['patch'], url_path='approve')
    def approve(self, request, pk=None):
        user = request.user
        approver_level = None

        approver_groups = user.groups.filter(name__startswith='approver-level-')
        print("Approver groups found:", approver_groups)
        if approver_groups.exists():
           group_name = approver_groups.first().name
           print("Using approver group:", group_name)
           try:
              # Extract the number (e.g., '1' from 'approver-level-1')
              level_str = group_name.split('-')[-1]
              approver_level = int(level_str)
           except (IndexError, ValueError):
             # Failed to parse the level number from the group name
             approver_level = None
        print("Approve called by user:", user.username)
        # print this particular user group or role 
        print("User groups:", user.groups.all())
        if approver_level is None:
            # fallback: infer from group name, or return forbidden
            return Response({"detail":"Approver level not found on user."}, status=status.HTTP_403_FORBIDDEN)

        # concurrency-safe approval
        with transaction.atomic():
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)

            if pr.status != PurchaseRequest.STATUS_PENDING:
                return Response({"detail":"Cannot approve a non-pending request."}, status=status.HTTP_400_BAD_REQUEST)
            # check if there's already a rejection
            if pr.approvals.filter(action=Approval.REJECTED).exists():
                pr.status = PurchaseRequest.STATUS_REJECTED
                pr.save(update_fields=['status'])
                return Response({"detail":"Request already rejected."}, status=status.HTTP_400_BAD_REQUEST)
            
            # prevent same level duplicate approval by this approver
            if Approval.objects.filter(purchase_request=pr, approver=user, level=approver_level).exists():
                return Response({"detail":"You already acted on this level."}, status=status.HTTP_400_BAD_REQUEST)

            # create approval record
            Approval.objects.create(
                purchase_request=pr,
                approver=user,
                level=approver_level,
                action=Approval.APPROVED,
                comment=request.data.get('comment','')
            )

            # mark last_approved_by
            pr.last_approved_by = user
            pr.save(update_fields=['last_approved_by','updated_at'])

            # check if all required approvals completed
            required = pr.required_approval_levels or getattr(settings,'REQUIRED_APPROVAL_LEVELS',[1,2])
            approved_levels = set(pr.approvals.filter(action=Approval.APPROVED).values_list('level', flat=True))

            if set(required).issubset(approved_levels):
                # finalize as approved and generate PO
                pr.status = PurchaseRequest.STATUS_APPROVED
                pr.save(update_fields=['status'])

                # Get linked Proforma instance
                if not pr.proforma:
                   return Response({"detail": "Cannot create PO: no Proforma linked."}, status=400)
                # generate PO record (PO file generation can be async)
                po = PurchaseOrder.objects.create(
                    purchase_request=pr, 
                    proforma=pr.proforma and Proforma.objects.filter(file=pr.proforma.name).first(),
                    vendor_name=pr.proforma.vendor_name if pr.proforma else '',
                    items=pr.proforma.items if pr.proforma else '',
                    total_amount=pr.proforma.total_amount if pr.proforma else 0,
                    generated_by=user, 
                    reference=f"PO-{pr.id}-{int(timezone.now().timestamp())}")
                
                serializer = self.get_serializer(pr)
                return Response(serializer.data, status=status.HTTP_200_OK)

            serializer = self.get_serializer(pr)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='reject')
    def reject(self, request, pk=None):
        user = request.user
        approver_level = None
        approver_groups = user.groups.filter(name__startswith='approver-level-')
        if approver_groups.exists():
            group_name = approver_groups.first().name
            try:
                # Extract the number (e.g., '1' from 'approver-level-1')
                level_str = group_name.split('-')[-1]
                approver_level = int(level_str)
            except (IndexError, ValueError):
                pass # approver_level remains None
        if approver_level is None:
            return Response(
                {"detail": "Approver level could not be determined. User must belong to a group like 'approver-level-1'."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        with transaction.atomic():
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)
            if pr.status != PurchaseRequest.STATUS_PENDING:
                return Response({"detail":"Cannot reject a non-pending request."}, status=status.HTTP_400_BAD_REQUEST)
            # create rejection
            if Approval.objects.filter(purchase_request=pr, approver=user, level=approver_level, action=Approval.REJECTED).exists():
                return Response({"detail":"You already rejected this request at your level."}, status=status.HTTP_400_BAD_REQUEST)

            Approval.objects.create(
                purchase_request=pr,
                approver=user,
                level=approver_level,
                action=Approval.REJECTED,
                comment=request.data.get('comment','')
            )
            # set final status immutable
            pr.status = PurchaseRequest.STATUS_REJECTED
            pr.save(update_fields=['status','updated_at'])
            serializer = self.get_serializer(pr)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='submit-receipt')
    def submit_receipt(self, request, pk=None):
        # Staff submits a receipt file. Only allowed if status is APPROVED (or sometimes pending based on business rules)
        pr = self.get_object()
        user = request.user
        if pr.created_by != user and not user_has_role(user, 'finance'):
            return Response({"detail":"Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if 'receipt' not in request.FILES:
            return Response({"detail":"Missing receipt file."}, status=status.HTTP_400_BAD_REQUEST)
        pr.receipt = request.FILES['receipt']
        pr.save(update_fields=['receipt','updated_at'])
        return Response(self.get_serializer(pr).data, status=status.HTTP_200_OK)

    # optionally: endpoints for listing pending / reviewed
    @action(detail=False, methods=['get'], url_path='pending')
    def list_pending(self, request):
        user = request.user
        qs = self.get_queryset().filter(status=PurchaseRequest.STATUS_PENDING)

        if user_has_role(user, 'approver'):
            approver_groups = user.groups.filter(name__startswith='approver-level-')
            if approver_groups.exists():
                level = int(approver_groups.first().name.split('-')[-1])
                qs = [pr for pr in qs if pr.required_approval_levels and level in pr.required_approval_levels]

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='reviewed')
    def reviewed(self, request):
        # show APPROVED or REJECTED
        qs = self.get_queryset().filter(status__in=[PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_REJECTED])
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

        instance = self.get_object()
        user = request.user
        
        # 1. Permission Check
        is_staff_or_creator = (
            user_has_role(user, 'staff') or instance.created_by == user
        )
        
        if not is_staff_or_creator:
            return Response(
                {"detail": "You do not have permission to edit this request."},
                status=status.HTTP_403_FORBIDDEN
            )
        # 3. Perform the Update using the serializer
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            # Save the updated data
            self.perform_update(serializer)
        
        # Return the updated instance data
        return Response(serializer.data, status=status.HTTP_200_OK)