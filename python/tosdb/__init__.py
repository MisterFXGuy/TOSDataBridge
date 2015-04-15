# Copyright (C) 2014 Jonathon Ogden     < jeog.dev@gmail.com >
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#   See the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License,
#   'LICENSE.txt', along with this program.  If not, see 
#   <http://www.gnu.org/licenses/>.

"""tosdb.py :  A Front-End / Wrapper for the TOS-DataBridge Library

Please refer to README.html for an explanation of the underlying library.
Please refer to PythonTutorial.html in /python/docs for a step-by-step 
walk-through. (currently this may be out-dated as the python layer is updated)

Class TOS_DataBlock (windows only): very similar to the 'block' approach of the
underlying library(again, see the README.html) except the interface is
explicitly object-oriented. A unique block id is handled by the object and the
unique C calls are handled accordingly. It also abstracts away most of the type
complexity of the underlying calls, raising TOSDB_Error exceptions ifinternal 
errors occur.

Class VTOS_DataBlock: same interface as TOS_DataBlock except it utilizes a thin
virtualization layer over UDP. Method calls are serialized and sent over a
phsyical/virtual network to a windows machine running the core implemenataion,
passing returned values back.

Those who want to access the TOS_DataBlock on linux while running Windows in
a virtual machine can abstract away nearly all the (unfortunately necessary)
non-portable parts of the core implementation.

In order to create a virtual block the 'local' windows implementation must
do everything it would normally do to instantiate a TOS_DataBlock (i.e connect
to a running TOSDataBridge service via init/connect) and then call
enable_virtualization() with an address tuple (addr,port) that the virtual
server ( _VTOS_DataServer ) will used to listen for 'remote' virtual blocks.

tosdb.py will attempt to load the non-portable _tosdb_win.py if on windows.
The following are some of the important calls imported from _tosdb_win.py that
control the underlying DLL:

  init() initializes the underlying library
  connect() connects to the library (init attemps this for you)
  connected() returns connection status (boolean)
  get_block_limit() returns block limit of the library's RawDataBlock factory
  set_block_limit() changes block limit of the library's RawDataBlock factory
  get_block_count() returns the current number of blocks in the library

  ********************************* IMPORTANT ********************************
  clean_up() de-allocates shared resources of the underlying library and
    Service. We attempt to clean up resources automatically for you on exit
    but in certain cases we can't, so its not guaranteed to happen. Therefore
    it's HIGHLY RECOMMENDED YOU CALL THIS FUNCTION before you exit.
  ********************************* IMPORTANT ********************************
"""

# _tosdb is how we deal with C++ header defined consts, those exported from the
# back-end libs, and '#define' compile-time consts necessary for C compatibility
from _tosdb import *  # also allows us to migrate away from ctypes when necessary
from .errors import *
from collections import namedtuple as _namedtuple
from threading import Thread as _Thread
from argparse import ArgumentParser as _ArgumentParser
from platform import system as _system
from abc import ABCMeta as _ABCMeta, abstractmethod as _abstractmethod
from sys import stderr as _stderr
import socket as _socket
import pickle as _pickle

class _TOS_DataBlock(metaclass=_ABCMeta):
    """ The DataBlock interface """
    @_abstractmethod
    def __str__(): pass
    @_abstractmethod
    def info(): pass
    @_abstractmethod
    def get_block_size(): pass
    @_abstractmethod
    def set_block_size(): pass
    @_abstractmethod
    def stream_occupancy(): pass
    @_abstractmethod
    def items(): pass
    @_abstractmethod
    def topics(): pass
    @_abstractmethod
    def add_items(): pass
    @_abstractmethod
    def add_topics(): pass
    @_abstractmethod
    def remove_items(): pass
    @_abstractmethod
    def remove_topics(): pass
    @_abstractmethod
    def get(): pass
    @_abstractmethod
    def stream_snapshot(): pass
    @_abstractmethod
    def stream_snapshot(): pass
    @_abstractmethod
    def item_frame(): pass
    @_abstractmethod
    def topic_frame(): pass
    #@_abstractmethod
    #def total_frame(): pass
    
_isWinSys = _system() in ["Windows","windows","WINDOWS"]

if _isWinSys: 
    from ._win import * # import the core implementation
    _TOS_DataBlock.register( TOS_DataBlock ) # and register as virtual subclass

_virtual_blocks = dict() 
_virtual_data_server = None

_vCREATE = '1'
_vCALL = '2'
_vDESTROY = '3'
_vFAIL = '4'
_vSUCCESS = '5'
_vSUCCESS_NT = '6'
_vDGRAM_SZ = 512 
_vTYPES = {'i':int,'s':str,'b':bool}
_vDELIM = b'*'
_vDELIM_S = _vDELIM.decode()

# move to _tosdb
_NTUP_TAG_ATTR = "_dont_worry_about_why_this_attribute_has_a_weird_name_"

class VTOS_DataBlock:
    """ The main object for storing TOS data. (VIRTUAL)   

    address: the adddress of the actual implementation
    size: how much historical data to save
    date_time: should block include date-time stamp with each data-point?
    timeout: how long to wait for responses from TOS-DDE server 

    Please review the attached README.html for details.
    """
    # check that address is 2-tuple
    def __init__( self, address, size = 1000, date_time = False,
                  timeout = DEF_TIMEOUT ):
        self._my_addr = address
        self._my_sock = _socket.socket( _socket.AF_INET, _socket.SOCK_DGRAM )
        self._my_sock.settimeout( timeout / 1000 )
        # in case __del__ is called during socket op
        self._name = None 
        self._name = self._call( _vCREATE, '__init__',
                                ('i',size), ('b',date_time), ('i',timeout) )
        
    def __del__( self ):
        try:
            if self._name:
                self._call( _vDESTROY )
            if self._my_sock:
                self._my_sock.close()
        except TOSDB_Error as e:
            print( e.args[0] )          

    def __str__( self ):
        return self._call( _vCALL, '__str__' )    
  
    def info(self):
        """ Returns a more readable dict of info about the underlying block """
        return self._call( _vCALL, 'info' )
    
    def get_block_size( self ):
        """ Returns the amount of historical data stored in the block """
        return self._call( _vCALL, 'get_block_size' )
    
    def set_block_size( self, sz ):
        """ Changes the amount of historical data stored in the block """
        self._call( _vCALL, 'set_block_size', ('i',sz) )
            
    def stream_occupancy( self, item, topic ):
        return self._call( _vCALL, 'stream_occupancy', ('s',item),
                           ('s',topic) )
    
    def items( self, str_max = MAX_STR_SZ ):
        """ Returns the items currently in the block (and not pre-cached).
        
        str_max: the maximum length of item strings returned
        returns -> list of strings 
        """
        return self._call( _vCALL, 'items', ('i',str_max) )          
              
    def topics( self,  str_max = MAX_STR_SZ ):
        """ Returns the topics currently in the block (and not pre-cached).
        
        str_max: the maximum length of topic strings returned  
        returns -> list of strings 
        """
        return self._call( _vCALL, 'topics', ('i',str_max) ) 
      
    
    def add_items( self, *items ):
        """ Add items ( ex. 'IBM', 'SPY' ) to the block.

        NOTE: if there are no topics currently in the block, these items will 
        be pre-cached and appear not to exist, until a valid topic is added.

        *items: any numer of item strings
        """               
        self._call( _vCALL, 'add_items', *zip('s'*len(items), items) )
       

    def add_topics( self, *topics ):
        """ Add topics ( ex. 'LAST', 'ASK' ) to the block.

        NOTE: if there are no items currently in the block, these topics will 
        be pre-cached and appear not to exist, until a valid item is added.

        *topics: any numer of topic strings
        """               
        self._call( _vCALL, 'add_topics', *zip('s'*len(topics), topics) )

    def remove_items( self, *items ):
        """ Remove items ( ex. 'IBM', 'SPY' ) from the block.

        NOTE: if there this call removes all items from the block the 
        remaining topics will be pre-cached and appear not to exist, until 
        a valid item is re-added.

        *items: any numer of item strings
        """
        self._call( _vCALL, 'remove_items', *zip('s'*len(items), items) )

    def remove_topics( self, *topics ):
        """ Remove topics ( ex. 'LAST', 'ASK' ) from the block.

        NOTE: if there this call removes all topics from the block the 
        remaining items will be pre-cached and appear not to exist, until 
        a valid topic is re-added.

        *topics: any numer of topic strings
        """
        self._call( _vCALL, 'remove_topics', *zip('s'*len(topics), topics) )
        
    def get( self, item, topic, date_time = False, indx = 0, 
             check_indx = True, data_str_max = STR_DATA_SZ ):
        """ Return a single data-point from the data-stream
        
        item: any item string in the block
        topic: any topic string in the block
        date_time: (True/False) attempt to retrieve a TOS_DateTime object   
        indx: index of data-points [0 to block_size), [-block_size to -1]
        check_indx: throw if datum doesn't exist at that particular index
        data_str_max: the maximum size of string data returned
        """
        return self._call( _vCALL, 'get', ('s',item), ('s',topic),
                           ('b',date_time), ('i',indx), ('b',check_indx),
                           ('i', data_str_max) )

    def stream_snapshot( self, item, topic, date_time = False, 
                         end = -1, beg = 0, smart_size = True, 
                         data_str_max = STR_DATA_SZ ):
        """ Return multiple data-points(a snapshot) from the data-stream
        
        item: any item string in the block
        topic: any topic string in the block
        date_time: (True/False) attempt to retrieve a TOS_DateTime object              
        end: index of least recent data-point ( end of the snapshot )
        beg: index of most recent data-point ( beginning of the snapshot )        
        smart_size: limits amount of returned data by data-stream's occupancy
        data_str_max: the maximum length of string data returned

        if date_time is True: returns-> list of 2tuple
        else: returns -> list              
        """
        return self._call( _vCALL, 'stream_snapshot', ('s',item),
                           ('s',topic), ('b',date_time), ('i',end), ('i',beg),
                           ('b',smart_size), ('i', data_str_max) )

def stream_snapshot_from_marker( self, item, topic, date_time = False, 
                                     beg = 0, margin_of_safety = 100,
                                     throw_if_data_lost = True,
                                     data_str_max = STR_DATA_SZ ):
        """ Return multiple data-points(a snapshot) from the data-stream,
        ending where the last call began

        It's likely the stream will grow between consecutive calls. This call
        guarantees to pick up where the last get(), stream_snapshot(), or
        stream_snapshot_from_marker() call ended (under a few assumptions, see
        below). 

        Internally the stream maintains a 'marker' that keeps track of
        the position of the last value pulled. It moves(increases) as the
        stream takes in new data and resets to the beginning of where data
        is last pulled from. This can be though of as an atomic operation
        with respect to the previous call as the act of retreiving the data
        and moving the marker are synchronized with internal stream
        operations (i.e new data can't be pushed in until they BOTH complete).

        There are three states - resulting from the following - to be aware of:
          1) a 'beg' value that is greater than the marker (even if beg = 0)
          2) a marker that moves through the entire stream and hits the bound
          3) passing a buffer that is too small for the whole range

        State (1) can be caused by passing in a beginning index that is past
        the current marker, or by passing in 0 when the marker has yet to
        move. 'None' will be returned.

        State (2) occurs when the marker doesn't get reset before enough data
        is pushed into the stream that it hits the bound (block_size); as the
        oldest data is popped of the back of the stream it is lost (the
        marker can't grow past the end of the stream). 

        State (3) occurs when an inadequately large enough buffer is used.
        The call handles buffer sizing for you by calling down to get the
        marker index, subtracting the beginning index passed in, and adding
        the margin_of_safety to assure the marker doesn't outgrow the
        buffer by the time the low-level retrieval operation takes place.
        The default value of 100 would mean that over 100 push operations
        would have to take place during this call, highly unlikely (if not
        impossible).

        In either case (state (2) or (3)) if throw_if_data_lost is True a
        TOSDB_Error will be thrown, if not the data that is available will
        be returned as normal. Obviously, the 'guarantee' would require
        the error condition be thrown.
        
        item: any item string in the block
        topic: any topic string in the block
        date_time: (True/False) attempt to retrieve a TOS_DateTime object                      
        beg: index of most recent data-point ( beginning of the snapshot )        
        margin_of_safety: (True/False) error margin for async stream growth
        throw_if_data_loss: (True/False) how to handle error states (see above)
        data_str_max: the maximum length of string data returned

        if beg > internal marker value: returns -> None        
        if date_time is True: returns-> list of 2tuple
        else: returns -> list              
        """
        return self._call( _vCALL, 'stream_snapshot_from_marker', ('s',item),
                          ('s',topic), ('b',date_time), ('i',beg),
                          ('i',margin_of_safety), ('b',throw_if_data_lost),
                          ('i', data_str_max) )
    
    def item_frame( self, topic, date_time = False, labels = True, 
                    data_str_max = STR_DATA_SZ,
                    label_str_max = MAX_STR_SZ ):
        """ Return all the most recent item values for a particular topic.

        topic: any topic string in the block
        date_time: (True/False) attempt to retrieve a TOS_DateTime object       
        labels: (True/False) pull the item labels with the values 
        data_str_max: the maximum length of string data returned
        label_str_max: the maximum length of item label strings returned

        if labels and date_time are True: returns-> namedtuple of 2tuple
        if labels is True: returns -> namedtuple
        if date_time is True: returns -> list of 2tuple
        else returns-> list
        """
        return self._call( _vCALL, 'item_frame', ('s',topic),
                           ('b',date_time), ('b',labels), ('i', data_str_max),
                           ('i', label_str_max) )   

    def topic_frame( self, item, date_time = False, labels = True, 
                     data_str_max = STR_DATA_SZ,
                     label_str_max = MAX_STR_SZ ):
        """ Return all the most recent topic values for a particular item:
  
        item: any item string in the block
        date_time: (True/False) attempt to retrieve a TOS_DateTime object       
        labels: (True/False) pull the topic labels with the values 
        data_str_max: the maximum length of string data returned
        label_str_max: the maximum length of topic label strings returned

        if labels and date_time are True: returns-> namedtuple of 2tuple
        if labels is True: returns -> namedtuple
        if date_time is True: returns -> list of 2tuple
        else returns-> list
        """
        return self._call( _vCALL, 'topic_frame', ('s',item),
                           ('b',date_time), ('b',labels), ('i', data_str_max),
                           ('i', label_str_max) )
##
##  !! need to find a way to pickle an iterable of namedtuples !!
##
##    def total_frame( self, date_time = False, labels = True, 
##                     data_str_max = STR_DATA_SZ,
##                     label_str_max = MAX_STR_SZ ):
##        """ Return a matrix of the most recent values:  
##        
##        date_time: (True/False) attempt to retrieve a TOS_DateTime object        
##        labels: (True/False) pull the item and topic labels with the values 
##        data_str_max: the maximum length of string data returned
##        label_str_max: the maximum length of label strings returned
##        
##        if labels and date_time are True: returns-> dict of namedtuple of 2tuple
##        if labels is True: returns -> dict of namedtuple
##        if date_time is True: returns -> list of 2tuple
##        else returns-> list
##        """
##        return self._call( _vCALL, 'total_frame', ('b',date_time),
##                           ('b',labels), ('i', data_str_max),
##                           ('i', label_str_max) )
   
    def _call( self, virt_type, method='', *arg_buffer ):
        
        self._check_for_delim(method, *arg_buffer)        
        if virt_type == _vCREATE:
            req_b = _encode_msg( _vCREATE, _pickle.dumps(arg_buffer) )
        elif virt_type == _vCALL:
            req_b = _encode_msg(_vCALL, self._name, method)
            if arg_buffer:
                req_b = _encode_msg( req_b, _pickle.dumps(arg_buffer) )
        elif virt_type == _vDESTROY:
            req_b = _encode_msg( _vDESTROY, self._name)
        else:
            raise TOSDB_VirtError( "invalid virt_type" )        
        
        if not _send_udp( self._my_sock, self._my_addr, req_b, _vDGRAM_SZ):
            raise TOSDB_VirtCommError("sendto() failed", "VTOS_DataBlock._call")
                  
        try:
            ret_b = _recv_udp( self._my_sock, _vDGRAM_SZ )[0]
        except _socket.timeout as e:
            raise TOSDB_VirtCommError("socket timed out","VTOS_DataBlock._call")
      
        args = ret_b.strip().split(_vDELIM)
        status = args[0].decode()
        if status == _vFAIL:
            #
            # need to make the error/failure return more robust
            # more info on what happened
            #
            raise TOSDB_VirtError( "failure status returned: ",
                                   "virt_type: " + str(virt_type),
                                   "method: " + str(method),
                                   "arg_buffer: " + str(arg_buffer) )
        
        if virt_type == _vCREATE:
            return args[1].decode()
        elif virt_type == _vCALL and len(args) > 1:
            if status == _vSUCCESS_NT:
                return _loadnamedtuple( args[1] )
            else:
                return _pickle.loads( args[1] )
        elif virt_type == _vDESTROY:
            return True

    @staticmethod
    def _check_for_delim( *strings ):
        for s in strings:
            if _vDELIM_S in s:
               raise TOSDB_ValueError("input contains a '" + _vDELIM_S + "'")

_TOS_DataBlock.register( VTOS_DataBlock )

   
def enable_virtualization( address ):
    global _virtual_data_server
    
    def _create_callback( addr, *args ):
        global _virtual_blocks
        print("DEBUG", "in _create_callback")
        blk = None
        try:
            print( *args )
            blk = TOS_DataBlock( *args ) 
            _virtual_blocks[blk._name] = (blk, addr)
            return blk._name                                       
        except Exception as e:
            print( "exception caught in _create_callback: ", e , file=_stderr )
            if blk:
                _virtual_blocks.pop(blk._name)
                del blk
            return False       

    def _destroy_callback( name ):
        global _virtual_blocks        
        try:
            blk = _virtual_blocks.pop( name )
            del blk
            return True
        except Exception as e:
            print( "exception caught in _destroy_callback: ", e, file=_stderr)
            return False

    def _call_callback( name, meth, *args):
        global _virtual_blocks    
        try:
            name = name.encode('ascii')           
            blk = _virtual_blocks[name][0]         
            meth = getattr(blk, meth )          
            ret = meth( *args )          
            return ret if ret else True
        except Exception as e:
            print( "exception caught in _call_callback: ", e, file=_stderr )
            return False
       
    class _VTOS_DataServer( _Thread ):
        
        def __init__( self, address, create_callback, destroy_callback,
                      call_callback):
            super().__init__()
            self._my_addr = address
            self._create_callback = create_callback
            self._destroy_callback = destroy_callback
            self._call_callback = call_callback
            self._rflag = False
            self._my_sock = _socket.socket( _socket.AF_INET, _socket.SOCK_DGRAM )
            self._my_sock.bind( address )
            
        def stop(self):
            self._rflag = False
            self._my_sock.close()

        def _handle_create( self, args, addr ):            
            upargs = _pickle.loads(args[1])                
            cargs = [ _vTYPES[t](v) for t,v in upargs ]            
            ret = self._create_callback( addr, *cargs )
            if ret:
                return _encode_msg( _vSUCCESS, ret )          

        def _handle_call( self, args ):
            if len(args) > 3:              
                upargs = _pickle.loads(args[3])
                cargs = [ _vTYPES[t](v) for t,v in upargs ]                
                ret = self._call_callback( args[1].decode(), args[2].decode(), 
                                           *cargs)
            else:
                ret = self._call_callback( args[1].decode(), args[2].decode() )            
            if ret:
                ret_b = _vSUCCESS.encode()
                if type(ret) != bool:
                    if hasattr(ret,_NTUP_TAG_ATTR):
                        ret_b = _encode_msg( _vSUCCESS_NT, _dumpnamedtuple(ret) )
                    else:
                        ret_b = _encode_msg( ret_b, _pickle.dumps(ret) )
                return ret_b          

        def _handle_destroy( self, args ):
            if self._virtual_destroy_callback( args[1].decode() ):
                return _vSUCCESS.encode()                 

        def run(self):
            self._rflag = True            
            while self._rflag:               
                try:            
                    dat, addr = _recv_udp( self._my_sock, _vDGRAM_SZ )            
                except _socket.timeout as e:
                    dat = None
                if not dat:
                    continue               
                args = dat.split(_vDELIM)
                msg_t = args[0].decode()
                r = None
                if msg_t == _vCREATE:
                    r = self._handle_create( args, addr )                    
                elif msg_t == _vCALL:
                    r = self._handle_call( args )                      
                elif msg_t == _vDESTROY:
                    r = self._handle_destroy( args )       
                _send_udp( self._my_sock, addr, r if r else _vFAIL.encode(), 
                           _vDGRAM_SZ )
                dat = addr = None              

    try:
        _virtual_data_server = _VTOS_DataServer( address, _create_callback,
                                                 _destroy_callback,
                                                 _call_callback )
        _virtual_data_server.start()      
    except Exception as e:
        raise TOSDB_VirtError( "(enable) virtualization error", e )

def disable_virtualization():
    global _virtual_data_server, _virtual_blocks
    try:
        if _virtual_data_server is not None:
           _virtual_data_server.stop()
           _virtual_data_server = None
           _virtual_blocks.clear()
    except Exception as e:
        raise TOSDB_VirtError( "(disable) virtualization error", e )    
    
def _dumpnamedtuple( nt ):
    n = type(nt).__name__
    od = nt.__dict__
    return _pickle.dumps( (n,tuple(od.keys()),tuple(od.values())) )

def _loadnamedtuple( nt):
    name,keys,vals = _pickle.loads( nt )
    ty = _namedtuple( name, keys )
    return ty( *vals )

def _recv_udp( sock, dgram_sz ):
    tot = b''   
    r, addr = sock.recvfrom( dgram_sz )
    while len(r) == dgram_sz:
        tot += r
        r, addr = sock.recvfrom( dgram_sz )
    tot += r
    return (tot,addr)    

def _send_udp( sock, addr, data, dgram_sz ):
    dl = len(data)
    snt = 0
    for i in range( 0, dl, dgram_sz ):
        snt += sock.sendto( data[i:i+dgram_sz], addr )          
    if dl % dgram_sz == 0:
        sock.sendto( b'', addr)
    return snt

def _encode_msg( *parts ):
    tot = b''
    for p in parts:
        tot += ( (p.encode() if type(p) is not bytes else p)  + _vDELIM )
    return tot.rstrip(_vDELIM)


if __name__ == "__main__" and _isWinSys:
    parser = _ArgumentParser()
    parser.add_argument( "--root", 
                         help = "root directory to search for the library" )
    parser.add_argument( "--path", help="the exact path of the library" )
    parser.add_argument( "-n", "--noinit", 
                         help="don't initialize the library automatically",
                         action="store_true" )
    args = parser.parse_args()   
    if not args.noinit:       
        if args.path:
            init( dllpath = args.path )
        elif args.root:
            init( root = args.root )
        else:
            print( "*WARNING* by not supplying --root, --path, or " +
                   "--noinit( -n ) arguments you are opting for a default " +
                   "search root of 'C:\\'. This will attempt to search " +
                   "the ENTIRE disk/drive for the tos-databridge library. " +
                   "It's recommended you restart the program with the " +
                   "library path (after --path) or a narrower directory " +
                   "root (after --root)." )                
            if input( "Do you want to continue anyway? (y/n): ") == 'y':
                init()
            else:
                print("- init(root='C:\\') aborted")
        


                