import errno
import select
import socket
import sys
import traceback
import time
import os

global cacheDict
global timeoutDict
cacheDict = {}
timeoutDict = {}

class ParsedRequest:
    def __init__(self):
        self.method = "NOVALUE"
        self.URL = "NOVALUE"
        self.version = "NOVALUE"
        self.headerList = []
    def __str__(self):
        result = "Request Method: " + self.method + '\r\n'
        result += "Request URL: " + self.URL + '\r\n'
        result += "Request Version: " + self.version + '\r\n'
        result += "Headers: --------------" + '\r\n'
        for s in self.headerList:
            result += s + '\r\n'
        return result
        
class Response:
    def __init__(self):
        self.version = "NOVERSION"
        self.time = ""
        self.statusCode = "NOSTATUS"
        self.statusPhrase = "NOPHRASE"
        self.headerLines = ["Server: Grant's Web-Server"]
        self.body = ""
    def __str__(self):
        result = self.version + ' ' + self.statusCode + ' ' + self.statusPhrase + '\r\n'
        result += 'Date: ' + self.time + '\r\n'
        for s in self.headerLines:
            result += s + '\r\n'
        result += '\r\n' + self.body
        return result


class Poller:
    """ Polling server """
    def __init__(self,port):
        ###print "-----------------------------------------------------------------------"
        self.host = ""
        self.port = port
        self.open_socket()
        self.clients = {}
        self.size = 1024
        self.configServer()

    def configServer(self):
        file = open("web.conf")
        global hostList
        global mediaList
        global parameter
        hostList = []
        mediaList = []
        parameter = 0
            
        while 1:
            line = file.readline()
            if not line:
                break
            list = line.split()
            if len(list) > 0:
                type = list[0]
                item = list[1] + ' ' + list[2]
                
                if type == "host":
                    item = item.split()[1]
                    hostList.append(item)
                if type == "media":
                    mediaList.append(item)
                if type == "parameter":
                    parameter = int(item.split()[1])
                    

    def open_socket(self):
        """ Setup the socket for incoming clients """
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
            self.server.bind((self.host,self.port))
            self.server.listen(5)
            self.server.setblocking(0)
        except socket.error, (value,message):
            print "socket error in open socket"
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
            TimeBefore = time.time()
            try:
                
                fds = self.poller.poll(timeout=1)
                
                    
            except:
                ###print "polling error?"
                return

            TimeAfter = time.time()
            Time = TimeAfter-TimeBefore
                
            if Time > .5:
                self.sweep()
            
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
        global timeoutDict
        while True:
            try:
                (client,address) = self.server.accept()
            except socket.error, (value,message):
                #print "socket error in server"
                # if socket blocks because no clients are available,
                # then return
                if value == errno.EAGAIN or errno.EWOULDBLOCK:
                    return
                print traceback.format_exc()
                sys.exit()
            # set client socket to be non blocking
            client.setblocking(0)
            self.clients[client.fileno()] = client
            timeoutDict[client.fileno()] = time.time()
            ###print self.clients
            self.poller.register(client.fileno(),self.pollmask)

    def handleClient(self,fd):
        cache = ""
        try:
            data = self.clients[fd].recv(self.size)
        except socket.error, (value,message):
            #print "socket error in handleClient"
            # if no data is available, move on to another client
            if value == errno.EAGAIN or errno.EWOULDBLOCK:
                return
            print traceback.format_exc()
            sys.exit()

        if data:
            global timeoutDict
            global cacheDict
            timeoutDict[fd] = time.time()
            if not fd in cacheDict:
                cacheDict[fd] = ""
            
            cacheDict[fd] += data
                
            if cacheDict[fd].endswith("\r\n\r\n"):
                    
                parsedRequest = self.parseHttp(cacheDict[fd]) 
                #print str(parsedRequest)
                
                response = self.determineResponse(parsedRequest)
                
                #print str(response)
                
                self.clients[fd].send(str(response))
                cacheDict[fd] = ""
                
                
        else:
            self.poller.unregister(fd)
            self.clients[fd].close()
            del self.clients[fd]
            if fd in timeoutDict:
                del timeoutDict[fd]

    def parseHttp(self, request):
		
        parsedRequest = ParsedRequest()
        
        lineList = request.splitlines()
        
        if len(lineList) > 0:
            requestLineList = lineList[0].split()
            if len(requestLineList) == 3:
                parsedRequest.method = requestLineList[0]
                global hostList
                parsedRequest.URL = hostList[0] + requestLineList[1]
                parsedRequest.version = requestLineList[2]
                
        if len(lineList) > 2:
            headLineList = []
            for i in range(1, len(lineList)):
                if(lineList[i] == ''):
                    break
                headLineList.append(lineList[i])
			
            parsedRequest.headerList = headLineList
                
        return parsedRequest
    
    def getContentType(self, request):
        if '.' in request.URL:
            contentType = request.URL.split('.')[1]
            global mediaList
            for s in mediaList:
                generalType = s.split()[0]
                specificType = s.split()[1]
                if contentType == generalType:
                    return specificType
            return ""
        else:
            return ""
            
            
    def get_time(self, t):
        gmt = time.gmtime(t)
        format = '%a, %d %b %Y %H:%M:%S GMT'
        time_string= time.strftime(format, gmt)
        return time_string 

    def determineResponse(self, parsedRequest):
        response = Response()
            
        response.version = parsedRequest.version
            
        t = time.time()
        response.time = self.get_time(t)
            
        #if the method or URI is empty... how do I get the URI?
        if (parsedRequest.method != "GET" and parsedRequest.method != "DELETE") or parsedRequest.URL == "NOVALUE":
            self.setBadRequestBody(response, parsedRequest)
                
        #if the web server does not implement the requested method
        elif parsedRequest.method == "DELETE":
            self.setNotImplementedBody(response, parsedRequest)

        else:
				
            contents = "File Not Found"
            if parsedRequest.URL == "web-server-testing/web/":
                parsedRequest.URL = "web-server-testing/web/index.html"
                
            try:    
                file = open(parsedRequest.URL)
                contents = file.read()
                #if web server cannot find requested file
                #404 Not Found                    
            except IOError:
                response.statusCode = "404"
                response.statusPhrase = "FILE NOT FOUND"
                response.headerLines.append("Last Modified: FILE NOT FOUND")
					
					
            contentType = self.getContentType(parsedRequest)
            response.headerLines.append("Content-Type: " + str(contentType))	   
            response.body = contents
            
            #if web server does not have permission to open requested file
            #403 Forbidden:
            if response.body == "Forbidden\n":
                response.statusCode = "403"
                response.statusPhrase = "FORBIDDEN"
                response.headerLines.append("Last Modified: FORBIDDEN")
                    
            response.headerLines.append("Content-Length: " + str(len(contents)))

            if response.statusCode == "NOSTATUS":
                response.statusCode = "200"
                response.statusPhrase = "OK"
                mod_time = os.stat(parsedRequest.URL).st_mtime
                response.headerLines.append("Last-Modified: " + str(self.get_time(mod_time)))

        return response

    def sweep(self):
        global timeoutDict
        deleteList = []
        #print timeoutDict
        for key, value in timeoutDict.iteritems():
            if key == self.server.fileno():
                continue
            currentTime = time.time()
            global parameter
            print currentTime - value
            if (currentTime - value) > parameter:
                deleteList.append(key)
                if key in self.clients:
                    self.poller.unregister(key)
                    self.clients[key].close()
                    del self.clients[key]
        for i in deleteList:
            if i in timeoutDict:
                del timeoutDict[i]
        return

    def setBadRequestBody(self, response, parsedRequest):
        response.statusCode = "400"
        response.statusPhrase = "BAD REQUEST"
        contentType = self.getContentType(parsedRequest)
        response.headerLines.append("Content-Type: " + str(contentType))
        response.body = "Bad Request"
        response.headerLines.append("Content-Length: " + str(len(response.body)))
        response.headerLines.append("Last-Modified: BAD REQUEST")

    def setNotImplementedBody(self, response, parsedRequest):
        response.statusCode = "501"
        response.statusPhrase = "NOT IMPLEMENTED"
        contentType = self.getContentType(parsedRequest)
        response.headerLines.append("Content-Type: " + str(contentType))
        response.body = "Not Implemented"
        response.headerLines.append("Content-Length: " + str(len(response.body)))
        response.headerLines.append("Last-Modified: NOT IMPLEMENTED")

        #Last test case is sending
        #GET
        #GET / HTTP/1.1\r\nHost: %s\r\n\r\n
        # / HTTP/1.1\r\nHost: %s\r\n\r\n
