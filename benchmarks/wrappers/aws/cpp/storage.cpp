
#include <memory>

#include <aws/core/auth/AWSCredentialsProvider.h>
#include <aws/core/client/ClientConfiguration.h>
#include <aws/s3/model/PutObjectRequest.h>
#include <aws/s3/model/GetObjectRequest.h>

#include <boost/interprocess/streams/bufferstream.hpp>

#include "storage.hpp"
#include "utils.hpp"

Storage Storage::get_client()
{
  Aws::Client::ClientConfiguration config;
  //config.region = "eu-central-1";
  config.caFile = "/etc/pki/tls/certs/ca-bundle.crt";

  std::cout << std::getenv("AWS_REGION") << std::endl;

  char const TAG[] = "LAMBDA_ALLOC";
  auto credentialsProvider = Aws::MakeShared<Aws::Auth::EnvironmentAWSCredentialsProvider>(TAG);
  Aws::S3::S3Client client(credentialsProvider, config);
  return Storage(std::move(client));
}

uint64_t Storage::download_file(Aws::String const &bucket, Aws::String const &key,
                        int &required_retries,
                        bool report_dl_time)
{
    

    Aws::S3::Model::GetObjectRequest request;
    request.WithBucket(bucket).WithKey(key);
    auto bef = timeSinceEpochMillisec();

    int retries = 0;
    //const int MAX_RETRIES = 500;
    const int MAX_RETRIES = 1500;
    while (retries < MAX_RETRIES) {
        auto outcome = this->_client.GetObject(request);
        if (outcome.IsSuccess()) {
            auto& s = outcome.GetResult().GetBody();
            uint64_t finishedTime = timeSinceEpochMillisec();
            // Perform NOP on result to prevent optimizations
            std::stringstream ss;
            ss << s.rdbuf();
            std::string first(" ");
            ss.get(&first[0], 1);
            required_retries = retries;
            if (report_dl_time) {
                return finishedTime - bef;
            } else {
                return finishedTime;
            }
        } else {
            retries += 1;
            //int sleep_time = retries;
            //if (retries > 100) {
            //    sleep_time = retries * 2;
            //}
            //std::this_thread::sleep_for(std::chrono::milliseconds(sleep_time));
        }
    }
    return 0;

}

uint64_t Storage::upload_random_file(Aws::String const &bucket,
                        Aws::String const &key,
                        int size, char* pBuf)
{
    /**
     * We use Boost's bufferstream to wrap the array as an IOStream. Usign a light-weight streambuf wrapper, as many solutions 
     * (e.g. https://stackoverflow.com/questions/13059091/creating-an-input-stream-from-constant-memory) on the internet
     * suggest does not work because the S3 SDK relies on proper functioning tellp(), etc... (for instance to get the body length).
     */
    const std::shared_ptr<Aws::IOStream> input_data = std::make_shared<boost::interprocess::bufferstream>(pBuf, size);

    Aws::S3::Model::PutObjectRequest request;
    request.WithBucket(bucket).WithKey(key);
    request.SetBody(input_data);
    uint64_t bef_upload = timeSinceEpochMillisec();
    Aws::S3::Model::PutObjectOutcome outcome = this->_client.PutObject(request);
    if (!outcome.IsSuccess()) {
        std::cerr << "Error: PutObject: " << outcome.GetError().GetMessage() << std::endl;
    }
    return bef_upload;
}
