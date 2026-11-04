from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import InventoryItemSerializer

_STORE = {}

class InventoryItemView(APIView):
    def get(self, request):
        serializer = InventoryItemSerializer(_STORE.values(), many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = InventoryItemSerializer(data=request.data)
        if serializer.is_valid():
            _STORE[serializer.validated_data["id"]] = serializer.validated_data
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
