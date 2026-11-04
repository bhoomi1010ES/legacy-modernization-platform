from rest_framework import serializers

class InventoryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField(max_length=64)
    quantity = serializers.IntegerField(min_value=0)
    unit_price = serializers.FloatField(min_value=0.0)
