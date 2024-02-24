import select
import socket
import sys
import queue
import time
import re


ip_address = sys.argv[1]
port = int(sys.argv[2])

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.setblocking(0)
server.bind((ip_address, port))
server.listen(5)

inputs = [server]
outputs = []
response_messages = {}

request_messages = {}

timestamps = {}

to_close = []

class response_mssg:
    def __init__(self, mssg, file, connection):
        self.mssg = mssg
        self.file = file
        self.connection = connection

def close_socket(s):
    """
    Function that closes socket passed and deallocates any resources it was allocated
    within the program.
    """
    if s in inputs:
        inputs.remove(s)
    if s in outputs:
        outputs.remove(s)

    s.close()

    del response_messages[s]
    del request_messages[s]
    del timestamps[s]

def check_times():
    """
    Function that checks if clients have been active within the last ~30 seconds.
    Closes any connection that has been inactive for more than 30 seconds.
    """
    for s in inputs:
        if s is server:
            continue
        elif time.time() - timestamps[s] >= 30:
            close_socket(s)

def format_response(request, connection, filename, valid, host, port):
    """
    Function that formats an HTTP response message based on the type and values of the request
    received.
    """
    curr_time = time.strftime("%a %b %d %X %Z %Y: ", time.localtime())
    response = None
    
    if not valid:
        mssg = "HTTP/1.0 400 Bad Request\r\nConnection: close\r\n\r\n"
        print(curr_time + str(host) + ":" + str(port) + " " + request.strip() + "; HTTP/1.0 400 Bad Request")
        response = response_mssg(mssg, None, "close")
    
    else:
        try:
            open(filename, "r")
            mssg = "HTTP/1.0 200 OK\r\nConnection: " + connection.strip() + "\r\n\r\n"
            print(curr_time + str(host) + ":" + str(port) + " " + request.strip() + "; HTTP/1.0 200 OK")
            response = response_mssg(mssg, filename, connection)
        
        except:
            mssg = "HTTP/1.0 404 Not Found\r\nConnection: " + connection.strip() + "\r\n\r\n"
            print(curr_time + str(host) + ":" + str(port) + " " + request.strip() + "; HTTP/1.0 404 Not Found")
            response = response_mssg(mssg, None, connection)
    
    return response

while True:
    check_times()
    readable, writable, exceptional = select.select(inputs, outputs, inputs, 30)

    for s in readable:
        if s is server:
            # accept connections, initialize entries and variables for that connection
            conn, addr = s.accept()
            conn.setblocking(0)
            inputs.append(conn)
            response_messages[conn] = queue.Queue()
            request_messages[conn] = ""
            timestamps[conn] = time.time()

        else:
            message = s.recv(1024).decode()
            if message and s not in to_close:
                if s not in outputs:
                    outputs.append(s)

                # client is active so update last timestamp
                timestamps[s] = time.time()
                request_messages[s] += message
                request_messages[s] = request_messages[s].replace("\r", "")
                complete_message = re.search("\n\n", request_messages[s])
                host, port = s.getpeername()
                connection = ""

                while complete_message and not request_messages[s] == "\n\n":
                    # ignore if only empty lines have been sent

                    response = ""

                    comp_mssg_str = request_messages[s][:complete_message.start()]
                    request_line = re.search("GET /?(.*) HTTP/1.0\s*\n?(.*)", comp_mssg_str)

                    if request_line:
                        filename = request_line.group(1)
                        if filename == "":
                            filename = "index.html"
                        header_line = re.search("connection:\s*(close|keep-alive).*", request_line.group(2), re.IGNORECASE)
                        if header_line:
                            connection = header_line.group(1)
                            response = format_response(comp_mssg_str.split("\n")[0], connection, filename, 1, host, port)

                        else:
                            connection = "close"
                            response = format_response(comp_mssg_str.split("\n")[0], "close", filename, 1, host, port)

                    else:
                        connection = "close"
                        response = format_response(comp_mssg_str.split("\n")[0], "close", None, 0, host, port)
                    
                    response_messages[s].put(response)
                    request_messages[s] = request_messages[s][complete_message.start() + 2:]
                    if connection == "close":
                        request_messages[s] = ""
                        to_close.append(s)
                        break
                    complete_message = re.search("\n\n", request_messages[s])

                comp_mssg = re.search("\n", request_messages[s])

                if comp_mssg and not request_messages[s] == "\n":
                    # if request line has been received, close it immediately if it's badly formatted
                    request_line = re.search("GET /?(.*) HTTP/1.0", request_messages[s][:comp_mssg.start()])

                    if not request_line:
                        response = format_response(request_messages[s][:comp_mssg.start()], "close", None, 0, host, port)

                        response_messages[s].put(response)
                        to_close.append(s)

                if request_messages[s] == "\n" or request_messages[s] == "\n\n":
                    # if only empty lines have been sent, then ignore them and keep connection open
                    request_messages[s] = ""

    
    for s in writable:
        if s in response_messages.keys() and response_messages[s].qsize():
            next_message = response_messages[s].get_nowait()
            s.send((next_message.mssg).encode())
            if next_message.file:
                s.send(open(next_message.file, "r").read().encode())
            if next_message.connection.lower() == "close":
                close_socket(s)

    for s in exceptional:
        close_socket(s)