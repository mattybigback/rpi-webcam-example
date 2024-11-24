#!/usr/bin/env python3
"""
Simple MJPEG streaming example using PyCamera2 with custom HTML page.

This script initializes the camera, starts an MJPEG stream using a custom output,
and serves a custom index.html file for the web interface.
"""

import threading
import http.server
import socketserver
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import Output

# Configuration
PORT = 8000  # Port number for HTTP server

class StreamingOutput(Output):
    def __init__(self):
        super().__init__()
        self.frame = None
        self.condition = threading.Condition()

    def outputframe(self, frame, keyframe=True, timestamp=None):
        with self.condition:
            self.frame = frame
            self.condition.notify_all()

def main():
    # Initialize the camera and configure settings
    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(main={"size": (640, 480)})
    picam2.configure(video_config)

    output = StreamingOutput()
    encoder = MJPEGEncoder()

    # Start recording and pass the output to our custom StreamingOutput
    picam2.start_recording(encoder, output)

    # Start the HTTP server in a separate thread
    http_server = CustomHTTPServer(('0.0.0.0', PORT), CustomHTTPRequestHandler, output)
    http_thread = threading.Thread(target=http_server.serve_forever)
    http_thread.start()
    print(f"Server started at http://0.0.0.0:{PORT}")

    try:
        # Keep the main thread alive
        http_thread.join()
    except KeyboardInterrupt:
        # Allow the user to stop the server with Ctrl+C
        print("Stopping server...")
    finally:
        # Ensure the camera stops recording and servers are shut down
        picam2.stop_recording()
        http_server.shutdown()
        http_thread.join()

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, output=None):
        self.output = output
        super().__init__(request, client_address, server)

    def do_GET(self):
        if self.path == '/':
            # Redirect to /index.html
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/stream.mjpg':
            # Handle MJPEG stream
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with self.output.condition:
                        self.output.condition.wait()
                        frame = self.output.frame
                    if frame:
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(frame)))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
            except Exception as e:
                print(f"Client disconnected: {e}")
        else:
            # Serve static files (e.g., index.html)
            super().do_GET()

class CustomHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, output):
        self.output = output
        super().__init__(server_address, RequestHandlerClass)

    def finish_request(self, request, client_address):
        self.RequestHandlerClass(request, client_address, self, output=self.output)

if __name__ == "__main__":
    # Start the script
    main()
