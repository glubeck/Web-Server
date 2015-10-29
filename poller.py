import errno
import select
import socket
import sys
import traceback
try:
    from http_parser.parser import HttpParser
except ImportError:
    from http_parser.pyparser import HttpParser

class Poller:
    """ Polling server """
    def __init__(self,port):
        self.host = ""
        self.port = port
        self.open_socket()
        self.clients = {}
        self.size = 1024

    def open_socket(self):
        """ Setup the socket for incoming clients """
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
            self.server.bind((self.host,self.port))
            self.server.listen(5)
            self.server.setblocking(0)
        except socket.error, (value,message):
            if self.server:
                self.server.close()
            print "Could not open socket: " + message
            sys.exit(1)

    def run(self):
        """ Use poll() to handle each incoming client."""
        self.poller = select.epoll()
        self.pollmask = select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR
        self.poller.register(self.server,self.pollmask)
        while True:
            # poll sockets
            try:
                fds = self.poller.poll(timeout=1)
            except:
                return
            for (fd,event) in fds:
                # handle errors
                if event & (select.POLLHUP | select.POLLERR):
                    self.handleError(fd)
                    continue
                # handle the server socket
                if fd == self.server.fileno():
                    self.handleServer()
                    continue
                # handle client socket
                result = self.handleClient(fd)

    def handleError(self,fd):
        self.poller.unregister(fd)
        if fd == self.server.fileno():
            # recreate server socket
            self.server.close()
            self.open_socket()
            self.poller.register(self.server,self.pollmask)
        else:
            # close the socket
            self.clients[fd].close()
            del self.clients[fd]

    def handleServer(self):
        # accept as many clients as possible
        while True:
            try:
                (client,address) = self.server.accept()
            except socket.error, (value,message):
                # if socket blocks because no clients are available,
                # then return
                if value == errno.EAGAIN or errno.EWOULDBLOCK:
                    return
                print traceback.format_exc()
                sys.exit()
            # set client socket to be non blocking
            client.setblocking(0)
            self.clients[client.fileno()] = client
            self.poller.register(client.fileno(),self.pollmask)

    def handleClient(self,fd):
        try:
            data = self.clients[fd].recv(self.size)
        except socket.error, (value,message):
            # if no data is available, move on to another client
            if value == errno.EAGAIN or errno.EWOULDBLOCK:
                return
            print traceback.format_exc()
            sys.exit()

        if data:

            file = open("web.conf")

            hostList = []
            mediaList = []
            parameterList = []
            
            while 1:
                line = file.readline()
                if not line:
                    break
                type = line.split(' ', 1)[0]
                if type == "host":
                    hostList.append(line)
                if type == "media":
                    mediaList.append(line)
                if type == "parameter":
                    parameterList.append(line)
                    
            print hostList
            print mediaList
            print parameterList
            p = HttpParser()

            nparsed = p.execute(data, len(data))
            
            #if the method or URI is empty... how do I get the URI?
            if not p.get_method() or not p.get_path():
                self.clients[fd].send('400 Bad Request\r\n\r\n')
                
            #if web server does not have permission to open requested file
            #403 Forbidden:

            #if web server cannot find requested file
            #404 Not Found

            #if the web server encounters any other error when trying to open
            #a file 500 Internal Server Error:

            #if the web server does not implement the requested method
            #501 Not Implemented:
            else:
                self.clients[fd].send(data)
        else:
            self.poller.unregister(fd)
            self.clients[fd].close()
            del self.clients[fd]
