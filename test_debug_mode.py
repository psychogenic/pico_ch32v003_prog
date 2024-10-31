
import singlewire_pio
import gc
from machine import Pin
from constants import *

gpio61 = Pin(18, mode=Pin.IN, pull=Pin.PULL_UP)

swio_sm = rp2.StateMachine(4, singlewire_pio.singlewire_pio, freq=12_000_000,
            sideset_base=gpio61, out_base=gpio61, set_base=gpio61, in_base=gpio61)

## Some unavoidable bit-twiddling
SIDE_PINDIR = const(29)
PIO0_BASE = const(0x50200000)
PIO1_BASE = const(0x50300000)
SM0_EXECCTRL = const(0x0cc)  # p 375
SM1_EXECCTRL = const(0xe4)
SM2_EXECCTRL = const(0xfc)
SM3_EXECCTRL = const(0x114)
SM4_EXECCTRL = const(0x0cc)  # p 375
SM5_EXECCTRL = const(0xe4)
SM6_EXECCTRL = const(0xfc)
SM7_EXECCTRL = const(0x114)

## Set side-set to control pindirs state machine
machine.mem32[PIO1_BASE + SM4_EXECCTRL] |= (1 << SIDE_PINDIR)

gc.disable()
gc.collect()

def b32(num):
    aa = (num & 0xFF000000) >> 24 
    bb= (num & 0x00FF0000) >> 16
    cc= (num & 0x0000FF00) >> 8
    dd= num & 0x000000FF
    print(f'{aa:#010b} {bb:#010b} {cc:#010b} {dd:#010b}')

def read_address(register):
    return(register << 1)
def write_address(register):
    return((register << 1) + 1)

inter_packet_delay = 60 

def send_write(address, data, delay=inter_packet_delay):
    swio_sm.put(write_address(address))
    swio_sm.put(data)
    swio_sm.active(1)
    time.sleep_us(delay)
    swio_sm.active(0)

def send_read(address, delay=inter_packet_delay):
    swio_sm.put(read_address(address))
    swio_sm.active(1)
    time.sleep_us(delay)
    swio_sm.active(0)
    return(swio_sm.get())

## blip?

def enter_debug_mode():
    send_write(WCH_DM_SHDWCFGR, OUTSTA)
    send_write(WCH_DM_CFGR, OUTSTA) ## OUTSTA: 0: The debug slave has output function.
    ## guarantee halt
    send_write(DM_CTRL, 0x80000001) ## 1: Debug module works properly 
    send_write(DM_CTRL, 0x80000003) ## 1: Debug module works properly 
    send_write(DM_CTRL, 0x80000001) ## 1: halt
    send_write(DM_CTRL, 0x80000001) ## 1: halt
    send_write(DM_CTRL, 0x80000001) ## 1: halt

def print_status_capabilities():
    status = send_read(DM_STATUS)
    print("status")
    b32(status)
    capabilities = send_read(WCH_DM_CPBR)
    print("capabilities")
    b32(capabilities)

## OK, now flash in the bootloader

def wait_for_done():
    is_busy = True
    while is_busy:
        abstract_control_status = send_read(DMABSTRACTCS)
        if (abstract_control_status & (1 << 12)) == 0:  ## abstract command busy bit
            is_busy = False

def write_word(address, data):
  
    send_write( DMABSTRACTAUTO, 0x00000000 )  #; // Disable Autoexec.
    
    send_write( DMDATA0, 0xe00000f4 )  #;   // DATA0's location in memory.
    send_write( DMCOMMAND, 0x00231008 )  #; // Copy data to x8
    send_write( DMDATA0, 0xe00000f8 )  #;   // DATA1's location in memory.
    send_write( DMCOMMAND, 0x00231009 )  #; // Copy address to x9

    send_write( DMDATA0, data )  #;
    send_write( DMDATA1, address )  #;
    
    send_write( DMPROGBUF0, 0x408c_4008 )  #  
    send_write( DMPROGBUF1, 0x9002_c188 )  #    
    
    send_write( DMCOMMAND, ((1 << 18) | (1<<21)) )  # execute program
    wait_for_done()

def read_word(address):
   
    send_write( DMABSTRACTAUTO, 0x00000000 )  #; // Disable Autoexec.
    
    send_write( DMDATA0, 0xe00000f4 )  #;   // DATA0's location in memory.
    send_write( DMCOMMAND, 0x00231008 )  #; // Copy data to x8
    send_write( DMDATA0, 0xe00000f8 )  #;   // DATA1's location in memory.
    send_write( DMCOMMAND, 0x00231009 )  #; // Copy address to x9

    send_write( DMDATA0, address )  # ;
    
    send_write( DMPROGBUF0, 0x4108_4008)   # lw x10 0(x10)   lw x10 0(x8) 
    send_write( DMPROGBUF1, 0x9002_c008)     # sw x10, 0(x8)
    # break 
    send_write( DMCOMMAND, ((1 << 18) | (1<<21)) )  # execute program
    wait_for_done()
    data = send_read(DMDATA0)
    return(data)


enter_debug_mode()
send_write( DMABSTRACTCS, 0x00000700 )  #;
#print_status_capabilities()
write_word(0x20000000, 0x12345678)
dm = send_read(DMABSTRACTCS)
b32(dm)

#print("0x12345678")
back = read_word(0x20000000)
print(hex(back))

mem = read_word(0x1FFFF7E0)
b32(mem)

# cs = send_read(DMABSTRACTCS)
# print(hex(cs))# 2, 27




def flash_bin(filename):
    binary_image = open(filename, "b").read()
    if len(binary_image) % 2 != 0:
        raise BaseException("Binary not even word length, handle me!")

    address = 0x08000000 
    first_time = True
    for wordstart in range(0, len(binary_image), 2):
        high_byte = binary_image[wordstart]
        low_byte = binary_image[wordstart+1]
        word_value = int(high_byte << 8) + int(low_byte)
        write_half_word(word_value, address)
        address = address + 2
    flash_ctrler = send_read(FLASH_CTLR)
    b32(flash_ctrler)
    print("disabling PG")
    send_write(FLASH_CTLR, flash_ctrler & ~(1 << 0) )
    flash_ctrler = send_read(FLASH_CTLR)
    b32(flash_ctrler)

def write_half_word(data, address_to_write):

    send_write( DMABSTRACTAUTO, 0x00000000 )  #; // Disable Autoexec.
	# Different address, so we don't need to re-write all the program regs.
	# sh x8,0(x9)  // Write to the address.
    send_write( DMPROGBUF0, 0x00849023 )  #;
    send_write( DMPROGBUF1, 0x00100073 )  #; // c.ebreak

    send_write( DMDATA0, address_to_write )  #;
    send_write( DMCOMMAND, 0x00231009 )  #; // Copy data to x9
    send_write( DMDATA0, data )  #;
    send_write( DMCOMMAND, 0x00271008 )  #; // Copy data to x8, and execute program.

    wait_for_done()

def unlock_flash():
    flash_ctrler = send_read(FLASH_CTLR)
    print("flash controller")
    b32(flash_ctrler)
    KEY1 = const(0x45670123)
    KEY2 = const(0xCDEF89AB)
    send_write( 0x40022004, KEY1 ) # FLASH->KEYR = 0x40022004
    send_write( 0x40022004, KEY2)  
    send_write( 0x40022008, KEY1 )  # OBKEYR = 0x40022008
    send_write( 0x40022008, KEY2 )  
    send_write( 0x40022024, KEY1 )  # MODEKEYR = 0x40022024
    send_write( 0x40022024, KEY2 )  #;

    # standard programming operations
    if True:
        flash_ctrler = send_read(FLASH_CTLR)
        print("flash controller")
        b32(flash_ctrler)

## reset and resume
def reset_and_resume():
    send_write( DM_CTRL, 0x80000001)  
    send_write( DM_CTRL, 0x80000001) 
    send_write( DM_CTRL, 0x00000001)  
    send_write( DM_CTRL, 0x40000001)





