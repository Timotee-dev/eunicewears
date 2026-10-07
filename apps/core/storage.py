"""Product photos on Cloudinary (Render's disk is wiped on every deploy). Used when CLOUDINARY_URL is set."""
import os
import secrets

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.text import slugify


@deconstructible
class CloudinaryMediaStorage(Storage):
    def _save(self, name, content):
        folder, filename = os.path.split(name.replace("\\", "/"))
        stem = slugify(os.path.splitext(filename)[0])[:40] or "photo"
        result = cloudinary.uploader.upload(
            content, folder=("eunice-wears/" + folder).rstrip("/"), public_id=stem + "-" + secrets.token_hex(4),
            resource_type="image", overwrite=False,
        )
        return result["public_id"] + "." + result["format"]

    def url(self, name):
        return cloudinary.utils.cloudinary_url(name, secure=True, fetch_format="auto", quality="auto")[0]

    def delete(self, name):
        cloudinary.uploader.destroy(os.path.splitext(name)[0], invalidate=True)

    def exists(self, name):
        return False

    def _open(self, name, mode="rb"):
        raise NotImplementedError("Photos are served straight from Cloudinary.")
