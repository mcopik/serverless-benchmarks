const puppeteer = require('puppeteer-core');
const path = require('path');
const { PassThrough } = require('stream');
const storage = require('./storage');

let storage_handler = new storage.storage();

const browserPath = path.join(__dirname, 'chromium/chrome-linux64/chrome');


exports.handler = async function(event) {
  const bucket = event.bucket.bucket;
  const input_prefix = event.bucket.input;
  const output_prefix = event.bucket.output;
  const input_file = event.object.input_file;

  // Create a read stream for the input HTML file
  let readStreamPromise = storage_handler.downloadStream(bucket, path.join(input_prefix, input_file));
  
  // Create a PassThrough stream to pipe the HTML content into Puppeteer
  const htmlStream = new PassThrough();

  // Create a write stream for the output PDF file
  let [writeStream, promise, uploadName] = storage_handler.uploadStream(bucket, path.join(output_prefix, 'output.pdf'));

  try {
    // Download the HTML file from storage
    const inputStream = await readStreamPromise;
    inputStream.pipe(htmlStream);

    // Launch Puppeteer and generate the PDF
    const browser = await puppeteer.launch({ executablePath: browserPath });
    const page = await browser.newPage();
    await page.setContent(await streamToString(htmlStream), { waitUntil: 'networkidle0' });
    const pdfBuffer = await page.pdf({ format: 'A4' });
    
    // Close Puppeteer
    await browser.close();

    // Pipe the PDF buffer into the write stream
    writeStream.write(pdfBuffer);
    writeStream.end();

    // Wait for upload to complete
    await promise;

    return { bucket: output_prefix, key: uploadName };
  } catch (error) {
    console.error('Error generating PDF:', error);
    throw error;
  }
};

// Utility function to convert a stream to a string
function streamToString(stream) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    stream.on('error', reject);
  });
}