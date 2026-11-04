from rest_framework import serializers
from .models import Room


class RoomSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()      # "Comp Lab D (309D)": label and room number together
    code = serializers.SerializerMethodField()

    def get_text(self, obj):
        from .rules import room_text
        return room_text(obj)

    def get_code(self, obj):
        from .rules import room_code
        return room_code(obj)

    class Meta:
        model = Room
        fields = [
            "text", "code",
            "id", "name", "building", "room_number", "label", "capacity", "capacity_is_estimate",
            "room_type", "department", "equipment", "is_accessible",
        ]
