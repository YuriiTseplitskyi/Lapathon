import io
from datetime import timedelta
from typing import Optional, Union

from minio import Minio
from minio.error import S3Error

from ingestion_job.app.core.settings import get_settings

class MinioClient:
    def __init__(self):
        self.settings = get_settings()
        
        self.client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )

    def upload_file(
        self,
        filename: str,
        data: Union[bytes, str],
        content_type: str = "application/octet-stream",
        bucket_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Uploads data to MinIO and returns the object name (or URL logic can be added).
        """
        if bucket_name is None:
            # Default to court bucket if not specified, or raise error?
            # For now default to court bucket as per previous logic logic
            bucket_name = self.settings.minio_bucket_court

        # Ensure bucket exists
        if not self.client.bucket_exists(bucket_name):
            try:
                self.client.make_bucket(bucket_name)
            except S3Error as err:
                print(f"[Minio] Error creating bucket {bucket_name}: {err}")
                return None

        # Convert string to bytes if needed
        if isinstance(data, str):
            data = data.encode("utf-8")
        
        data_stream = io.BytesIO(data)
        length = len(data)

        try:
            self.client.put_object(
                bucket_name,
                filename,
                data_stream,
                length,
                content_type=content_type,
            )
            # Construct a URL or simple reference. 
            # For local dev, we might just return the s3 path.
            return f"minio://{bucket_name}/{filename}"
        except S3Error as err:
            print(f"[Minio] Upload failed for {filename}: {err}")
            return None

    def get_presigned_url(self, filename: str, bucket_name: Optional[str] = None) -> Optional[str]:
        if bucket_name is None:
            bucket_name = self.settings.minio_bucket_court
            
        try:
            return self.client.get_presigned_url(
                "GET",
                bucket_name,
                filename,
                expires=timedelta(hours=1),
            )
        except S3Error as err:
            print(f"[Minio] Failed to generate URL for {filename}: {err}")
            return None
