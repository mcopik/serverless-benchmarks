
#include <cstdint>

#include <aws/core/utils/memory/stl/AWSString.h>
#include <aws/s3/S3Client.h>

class Storage
{
  Aws::S3::S3Client _client;
public:

  Storage(Aws::S3::S3Client && client):
    _client(client)
  {}

  static Storage get_client();

  uint64_t download_file(Aws::String const &bucket,
                          Aws::String const &key,
                          int &required_retries,
                          bool report_dl_time);

  uint64_t upload_random_file(Aws::String const &bucket,
                          Aws::String const &key,
                          int size, char* pBuf);

};

