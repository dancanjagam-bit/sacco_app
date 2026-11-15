from io import BytesIO

from django.http import HttpResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import AuditLog
from members.models import Member, MemberProfilePhoto


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
PHOTO_SIZE = (512, 512)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def profile_photo(request):
    try:
        member = request.user.member_profile
    except Member.DoesNotExist:
        return Response({"error": "A member profile is required."}, status=403)

    if request.method == "GET":
        photo = MemberProfilePhoto.objects.filter(member=member).first()
        if photo is None:
            return Response({"error": "No profile photo has been uploaded."}, status=404)
        return HttpResponse(
            bytes(photo.image),
            content_type="image/jpeg",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    if request.method == "DELETE":
        deleted, _ = MemberProfilePhoto.objects.filter(member=member).delete()
        if deleted:
            AuditLog.log(request.user, "member_update", "Profile photo removed", request=request)
        return Response(status=204)

    upload = request.FILES.get("photo")
    if not upload or upload.size > MAX_UPLOAD_BYTES:
        return Response({"error": "Choose an image no larger than 5 MB."}, status=400)

    try:
        with Image.open(upload, formats=["JPEG", "PNG", "WEBP"]) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS or getattr(source, "is_animated", False):
                return Response({"error": "Choose a still image with at most 20 megapixels."}, status=400)
            image = ImageOps.exif_transpose(source)
            image.thumbnail(PHOTO_SIZE)
            rgba = image.convert("RGBA")
            clean = Image.new("RGB", image.size, "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            clean.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return Response({"error": "Choose a valid JPEG, PNG, or WebP image."}, status=400)

    MemberProfilePhoto.objects.update_or_create(member=member, defaults={"image": output.getvalue()})
    AuditLog.log(request.user, "member_update", "Profile photo updated", request=request)
    return Response({"has_profile_photo": True})
