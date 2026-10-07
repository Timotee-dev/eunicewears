"""Product photos on Cloudinary. Render's disk is wiped on every deploy, so production must not keep uploads locally.
Switched on automatically when CLOUDINARY_URL is set (see config/settings.py)."""
import os
import secrets

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.text import slugify

ROOT_FOLDER = "eunice-wears"


@deconstructible
class CloudinaryMediaStorage(Storage):
    def _save(self, name: str, content) -> str:
        if hasattr(content, "seek"):
            content.seek(0)  # validation has already read the file once
        folder, filename = os.path.split(name.replace("\\", "/"))
        stem = slugify(os.path.splitext(filename)[0])[:40] or "photo"
        result = cloudinary.uploader.upload(
            content, folder=f"{ROOT_FOLDER}/{folder}".rstrip("/"), public_id=f"{stem}-{secrets.token_hex(4)}",
            resource_type="image", overwrite=False,
        )
        return f"{result['public_id']}.{result['format']}"  # what gets stored in the database

    def url(self, name: str) -> str:
        # f_auto/q_auto: Cloudinary serves WebP/AVIF at a sensible quality to browsers that support them.
        return cloudinary.utils.cloudinary_url(name, secure=True, fetch_format="auto", quality="auto")[0]

    def delete(self, name: str) -> None:
        cloudinary.uploader.destroy(os.path.splitext(name)[0], invalidate=True)

    def exists(self, name: str) -> bool:
        return False  # every upload gets a random suffix, so names never collide

    def _open(self, name, mode="rb"):
        raise NotImplementedError("Photos are served straight from Cloudinary.")
