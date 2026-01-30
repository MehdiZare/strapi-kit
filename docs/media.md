# Media Upload/Download

Complete guide to working with media files in py-strapi.

## Overview

py-strapi provides comprehensive media file operations for Strapi's media library, including:

- File uploads with metadata
- Batch uploads
- File downloads with streaming
- Media library queries
- Metadata updates
- File deletion

All operations support both **Strapi v4 and v5** with automatic version detection.

## Upload Operations

### Basic Upload

Upload a single file to the media library:

```python
from py_strapi import SyncClient, StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token"
)

with SyncClient(config) as client:
    media = client.upload_file("image.jpg")

    print(f"Uploaded: {media.name}")
    print(f"URL: {media.url}")
    print(f"Size: {media.size} KB")
    print(f"MIME: {media.mime}")
```

### Upload with Metadata

Add alt text, captions, and other metadata:

```python
media = client.upload_file(
    "hero-image.jpg",
    alternative_text="Hero image for homepage",
    caption="Main banner showcasing our product"
)

print(f"Alt text: {media.alternative_text}")
print(f"Caption: {media.caption}")
```

### Upload to Folder

Organize uploads into folders:

```python
media = client.upload_file(
    "thumbnail.jpg",
    folder="thumbnails"  # Folder ID
)
```

### Attach to Entity

Upload and immediately attach to a content entity:

```python
# Upload cover image for an article
cover = client.upload_file(
    "cover.jpg",
    ref="api::article.article",  # Model name
    ref_id="abc123",              # Entity ID (documentId or numeric)
    field="cover"                 # Field name
)

# The file is now attached to the article's "cover" field
```

### Batch Upload

Upload multiple files sequentially:

```python
files = ["image1.jpg", "image2.jpg", "image3.jpg"]

media_list = client.upload_files(
    files,
    folder="gallery",
    alternative_text="Gallery image"  # Shared metadata
)

print(f"Uploaded {len(media_list)} files")

for media in media_list:
    print(f"- {media.name}: {media.url}")
```

**Error Handling:**

If one file fails during batch upload, a `MediaError` is raised with details about which file failed. Previously uploaded files are **NOT** rolled back.

```python
from py_strapi.exceptions import MediaError

try:
    media_list = client.upload_files(files)
except MediaError as e:
    print(f"Upload failed: {e}")
    # Error message includes: which file, at what index, how many succeeded
```

## Download Operations

### Download to Bytes

Download file content to memory:

```python
media = client.get_media(42)
content = client.download_file(media.url)

print(f"Downloaded {len(content)} bytes")

# Use the bytes data
with open("local_copy.jpg", "wb") as f:
    f.write(content)
```

### Download and Save

Download directly to a file:

```python
media = client.get_media(42)

client.download_file(
    media.url,
    save_path="downloaded_image.jpg"
)

print("File saved successfully")
```

### Download from Absolute URL

Works with both relative and absolute URLs:

```python
# Relative URL (prepends base_url)
content = client.download_file("/uploads/image.jpg")

# Absolute URL (CDN, external storage)
content = client.download_file("https://cdn.example.com/uploads/image.jpg")
```

### Streaming for Large Files

Downloads use streaming automatically to handle large files efficiently:

```python
# Even for large video files, memory usage is minimal
video_content = client.download_file("/uploads/large_video.mp4")
```

## Media Library Operations

### List All Media

Query the media library:

```python
response = client.list_media()

print(f"Total media files: {response.meta.pagination.total}")

for media in response.data:
    attrs = media.attributes
    print(f"{attrs['name']}: {attrs['url']}")
```

### List with Filters

Use `StrapiQuery` to filter results:

```python
from py_strapi.models import StrapiQuery, FilterBuilder

# Filter by MIME type
query = StrapiQuery().filter(
    FilterBuilder().eq("mime", "image/jpeg")
)
response = client.list_media(query)

# Complex filters
query = (StrapiQuery()
    .filter(FilterBuilder()
        .eq("mime", "image/jpeg")
        .gt("size", 100))  # Size in KB
    .sort_by("createdAt", SortDirection.DESC)
    .paginate(page=1, page_size=10))

response = client.list_media(query)
```

### Get Specific Media

Retrieve details for a single media file:

```python
# By numeric ID
media = client.get_media(42)

# By documentId (v5)
media = client.get_media("media_abc123")

print(f"Name: {media.name}")
print(f"URL: {media.url}")
print(f"Size: {media.size} KB")
print(f"Dimensions: {media.width}x{media.height}")

# Access format variants (thumbnail, small, medium, large)
if media.formats:
    thumb = media.formats.get("thumbnail")
    if thumb:
        print(f"Thumbnail URL: {thumb.url}")
        print(f"Thumbnail size: {thumb.width}x{thumb.height}")
```

## Update Operations

### Update Metadata

Modify media metadata without re-uploading:

```python
updated = client.update_media(
    42,
    alternative_text="Updated alt text",
    caption="Updated caption",
    name="new-filename.jpg"
)

print(f"Updated: {updated.name}")
```

### Partial Updates

Only provide fields you want to change:

```python
# Update only alt text
updated = client.update_media(
    42,
    alternative_text="New alt text"
)

# Update only caption
updated = client.update_media(
    42,
    caption="New caption"
)
```

## Delete Operations

### Delete Media File

Remove a file from the media library:

```python
client.delete_media(42)
print("Media file deleted")
```

**Note:** Deleting media also removes references from entities using it.

```python
from py_strapi.exceptions import NotFoundError, MediaError

try:
    client.delete_media(999)
except NotFoundError:
    print("Media not found")
except MediaError as e:
    print(f"Deletion failed: {e}")
```

## Async Operations

All media methods have async equivalents:

```python
import asyncio
from py_strapi import AsyncClient, StrapiConfig

async def main():
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="your-token"
    )

    async with AsyncClient(config) as client:
        # Upload
        media = await client.upload_file(
            "image.jpg",
            alternative_text="Alt text"
        )

        # Batch upload
        media_list = await client.upload_files(
            ["img1.jpg", "img2.jpg", "img3.jpg"]
        )

        # Download
        content = await client.download_file(media.url)

        # List
        response = await client.list_media()

        # Get
        media = await client.get_media(42)

        # Update
        updated = await client.update_media(
            42,
            alternative_text="New alt"
        )

        # Delete
        await client.delete_media(42)

asyncio.run(main())
```

## Complete Example

Upload, manage, and download media files:

```python
from py_strapi import SyncClient, StrapiConfig
from py_strapi.models import StrapiQuery, FilterBuilder
from py_strapi.exceptions import MediaError

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token"
)

with SyncClient(config) as client:
    # Upload images for an article
    hero = client.upload_file(
        "hero-image.jpg",
        alternative_text="Article hero image",
        caption="Main article banner"
    )

    gallery_files = [
        "gallery1.jpg",
        "gallery2.jpg",
        "gallery3.jpg"
    ]

    try:
        gallery = client.upload_files(
            gallery_files,
            folder="article-gallery"
        )
        print(f"Uploaded {len(gallery)} gallery images")
    except MediaError as e:
        print(f"Gallery upload failed: {e}")

    # Create article with hero image
    article_data = {
        "title": "My Article",
        "content": "Article content here",
        "hero": hero.id  # Reference uploaded media
    }
    article = client.create("articles", article_data)
    print(f"Article created with hero image")

    # List all images in the gallery folder
    query = (StrapiQuery()
        .filter(FilterBuilder()
            .eq("mime", "image/jpeg")
            .contains("name", "gallery"))
        .sort_by("createdAt"))

    response = client.list_media(query)
    print(f"Found {len(response.data)} gallery images")

    # Download hero image for processing
    hero_content = client.download_file(
        hero.url,
        save_path="local_hero.jpg"
    )
    print(f"Downloaded hero image: {len(hero_content)} bytes")

    # Update metadata
    updated_hero = client.update_media(
        hero.id,
        alternative_text="Updated hero image alt text"
    )
    print(f"Updated hero metadata")
```

## Advanced Usage

### Custom Timeout for Large Uploads

Override timeout for large files:

```python
# Note: This feature is planned for future implementation
# For now, adjust the global timeout in config:

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    timeout=300.0  # 5 minutes for large uploads
)
```

### Progress Tracking

Progress callbacks are planned for future versions. For now, use batch uploads with try/except to track progress:

```python
uploaded = []
failed = []

for file_path in large_file_list:
    try:
        media = client.upload_file(file_path)
        uploaded.append(media)
        print(f"Progress: {len(uploaded)}/{len(large_file_list)}")
    except MediaError as e:
        failed.append((file_path, str(e)))

print(f"Uploaded: {len(uploaded)}, Failed: {len(failed)}")
```

## Error Handling

### Common Exceptions

```python
from py_strapi.exceptions import (
    MediaError,
    NotFoundError,
    AuthenticationError,
    ValidationError
)

try:
    # Upload
    media = client.upload_file("image.jpg")

except FileNotFoundError:
    print("Local file not found")

except MediaError as e:
    print(f"Upload failed: {e}")
    # Could be: file too large, unsupported format, etc.

except AuthenticationError:
    print("Invalid API token")

except ValidationError as e:
    print(f"Invalid parameters: {e}")
```

### Error Details

All exceptions include details:

```python
try:
    client.upload_file("huge_file.mp4")
except MediaError as e:
    print(f"Error: {e}")
    if e.details:
        print(f"Details: {e.details}")
    # Example details: {"maxFileSize": "50MB", "receivedSize": "200MB"}
```

## Model Reference

### MediaFile

The `MediaFile` model represents uploaded media:

```python
media = client.get_media(42)

# Core fields
media.id              # int: Numeric ID
media.document_id     # str | None: documentId (v5 only)
media.name            # str: Filename
media.url             # str: File URL
media.mime            # str: MIME type
media.size            # float: Size in KB
media.ext             # str: File extension
media.hash            # str: File hash
media.provider        # str: Storage provider

# Optional fields
media.alternative_text  # str | None: Alt text
media.caption          # str | None: Caption
media.width            # int | None: Image width
media.height           # int | None: Image height

# Formats (image variants)
media.formats          # dict[str, MediaFormat] | None

# Timestamps
media.created_at       # datetime | None
media.updated_at       # datetime | None
```

### MediaFormat

Image format variants (thumbnail, small, medium, large):

```python
if media.formats:
    thumb = media.formats["thumbnail"]

    thumb.name         # str: Format name
    thumb.url          # str: Format URL
    thumb.width        # int | None: Width
    thumb.height       # int | None: Height
    thumb.size         # float: Size in KB
    thumb.mime         # str: MIME type
```

## Best Practices

1. **Always use context managers**: Ensures proper cleanup

   ```python
   with SyncClient(config) as client:
       # Your code here
   ```

2. **Handle errors explicitly**: Don't let exceptions propagate silently

   ```python
   try:
       media = client.upload_file("image.jpg")
   except MediaError as e:
       logger.error(f"Upload failed: {e}")
       # Handle gracefully
   ```

3. **Use metadata**: Set alt text for accessibility

   ```python
   media = client.upload_file(
       "product.jpg",
       alternative_text="Product photo showing features"
   )
   ```

4. **Organize with folders**: Keep media library organized

   ```python
   client.upload_file("thumb.jpg", folder="thumbnails")
   ```

5. **Validate before upload**: Check file exists and size

   ```python
   from pathlib import Path

   file_path = Path("image.jpg")
   if not file_path.exists():
       print("File not found")
   elif file_path.stat().st_size > 50 * 1024 * 1024:  # 50MB
       print("File too large")
   else:
       media = client.upload_file(file_path)
   ```

6. **Clean up unused media**: Delete unused files to save storage

   ```python
   # Before deleting, ensure no entities reference it
   client.delete_media(old_media_id)
   ```

## Strapi v4 vs v5

py-strapi handles version differences automatically:

| Feature          | Strapi v4            | Strapi v5            | py-strapi          |
| ---------------- | -------------------- | -------------------- | ------------------ |
| Media ID         | Numeric `id`         | `id` + `documentId`  | Both supported     |
| Upload endpoint  | `/api/upload`        | `/api/upload`        | Same               |
| Response format  | Nested `attributes`  | Flattened            | Auto-normalized    |
| List endpoint    | `/api/upload/files`  | `/api/upload/files`  | Same               |
| Update endpoint  | `/api/upload/:id`    | `/api/upload/:id`    | Same               |

All media operations work identically across versions.

## Limitations

- **Strapi upload size limits**: Respect Strapi's configured max file size
- **No parallel uploads**: `upload_files()` uploads sequentially (parallel uploads planned for future)
- **No rollback**: Failed batch uploads don't delete previously uploaded files
- **Provider-specific features**: Advanced features depend on storage provider (local, S3, etc.)

## Future Enhancements

Planned for future releases:

- Progress callbacks for large uploads
- Parallel batch uploads
- Media validation before upload (MIME, size checks)
- Advanced folder management
- Thumbnail generation control
- Image optimization options
