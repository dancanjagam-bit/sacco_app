from decimal import Decimal

from rest_framework import serializers


class CrewAssignmentInput(serializers.Serializer):
    vehicle = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    route = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    driver = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    conductor = serializers.IntegerField(
        min_value=1, max_value=2**63 - 1, required=False, allow_null=True,
    )
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()

    def to_internal_value(self, data):
        # Existing staff clients send an empty string when no conductor is selected.
        if hasattr(data, "get") and data.get("conductor") == "":
            data = data.copy()
            data["conductor"] = None
        return super().to_internal_value(data)

    def validate(self, data):
        if data["ends_at"] <= data["starts_at"]:
            raise serializers.ValidationError("End must be after start.")
        if data.get("conductor") == data["driver"]:
            raise serializers.ValidationError("Driver and conductor must be different users.")
        return data


class TransportCollectionInput(serializers.Serializer):
    assignment = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    recorded_by = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    client_key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    notes = serializers.CharField(
        max_length=300, allow_blank=True, required=False, default="", trim_whitespace=False,
    )


class TransportExpenseInput(TransportCollectionInput):
    category = serializers.CharField(max_length=60)


class TransportReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


