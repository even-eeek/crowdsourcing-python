"""
This module represents a device.
"""

from threading import Event, Thread, Condition, Lock

#barrier
class Barrier(object):
    """ reentrant barrier, used a conditional variable"""

    def __init__(self, num_threads=0):
        self.num_threads = num_threads
        self.count_threads = self.num_threads
        # block/unblock threads
        self.cond = Condition()

    def wait(self):
        """docstring"""
        # critical entry
        self.cond.acquire()
        self.count_threads -= 1
        if self.count_threads == 0:
            # unblock all threads
            self.cond.notify_all()
            self.count_threads = self.num_threads
        else:
            # block the thread and free the lock
            self.cond.wait()
        # critical exit
        self.cond.release()

class Device(object):
    """
    Class that represents a device.
    """
    #static variables
    bariera_devices = Barrier()
    locks = []

    def __init__(self, device_id, sensor_data, supervisor):
        """
        Constructor.

        @type device_id: Integer
        @param device_id: the unique id of this node; between 0 and N-1

        @type sensor_data: List of (Integer, Float)
        @param sensor_data: a list containing (location, data) as measured
        by this device

        @type supervisor: Supervisor
        @param supervisor: the testing infrastructure's control and validation
        component
        """
        self.device_id = device_id
        self.sensor_data = sensor_data
        self.supervisor = supervisor
        #script from the position i in the scripts list corresponds to
        #location i from the location list
        self.scripts = []
        self.locations = []
        #total number of scripts given
        self.nr_scripturi = 0 
        self.script_crt = 0

        #events that notify when a thread has stopped receiving
        # scripts from the current timepoint
        self.timepoint_done = Event()

        #neighbour list from the current timepoint
        self.neighbours = []
        self.event_neighbours = Event()
        self.lock_script = Lock()
        self.bar_thr = Barrier(8)

        #create and start the threads for the device scripts
        self.thread = DeviceThread(self, 1)
        self.thread.start()
        self.threads = []
        for _ in range(7):
            tthread = DeviceThread(self, 0)
            self.threads.append(tthread)
            tthread.start()

    def __str__(self):
        """
        Pretty prints this device.

        @rtype: String
        @return: a string containing the id of this device
        """
        return "Device %d" % self.device_id

    def setup_devices(self, devices):
        """
        Setup the devices before simulation begins.

        @type devices: List of Device
        @param devices: list containing all devices
        """
        #instantiate the barrier for the devices
        Device.bariera_devices = Barrier(len(devices))
        if Device.locks == []:
            for _ in range(self.supervisor.supervisor.testcase.num_locations):
                Device.locks.append(Lock())

    def assign_script(self, script, location):
        """
        Provide a script for the device to execute.

        @type script: Script
        @param script: the script to execute from now on at each timepoint;
        None if the
            current timepoint has ended

        @type location: Integer
        @param location: the location for which the script is interested in
        """
        if script is not None:
            self.scripts.append(script)
            self.locations.append(location)
            self.nr_scripturi += 1
        else:
            self.timepoint_done.set()

    def get_data(self, location):
        """
        Returns the pollution value this device has for the given location.

        @type location: Integer
        @param location: a location for which obtain the data

        @rtype: Float
        @return: the pollution value
        """
        return self.sensor_data[location] if location in \
        self.sensor_data else None

    def set_data(self, location, data):
        """
        Sets the pollution value stored by this device for the given location.

        @type location: Integer
        @param location: a location for which to set the data

        @type data: Float
        @param data: the pollution value
        """
        if location in self.sensor_data:
            self.sensor_data[location] = data

    def shutdown(self):
        """
        Instructs the device to shutdown (terminate all threads). This method
        is invoked by the tester. This method must block until all the threads
        started by this device terminate.
        """
        self.thread.join()
        for tthread in self.threads:
            tthread.join()


class DeviceThread(Thread):
    """
    Class that implements the device's worker thread.
    """

    def __init__(self, device, first):
        """
        Constructor.

        @type device: Device
        @param device: the device which owns this thread
        """
        Thread.__init__(self, name="Device Thread %d" % device.device_id)
        self.device = device
        self.first = first

    def run(self):
        while True:
            #only one thread calls the methods for the neighbours handling and that start sending the scripts from the supervisor
            if self.first == 1:
                # get the current neighbourhood
                self.device.neighbours = self.device.supervisor.get_neighbours()
                self.device.script_crt = 0
                self.device.event_neighbours.set()

            # wait for the neighbours
            self.device.event_neighbours.wait()

            if self.device.neighbours is None:
                break

            #wait for all the sripts
            self.device.timepoint_done.wait()

            while True:
                #the thread wants to reserve a spot
                self.device.lock_script.acquire()
                index = self.device.script_crt
                self.device.script_crt += 1
                self.device.lock_script.release()

                #if no more scripts, the thread is in standby so exit the while loop
                if index >= self.device.nr_scripturi:
                    break
                #the script and the location reserved for the current thread

                location = self.device.locations[index]
                script = self.device.scripts[index]

                #two scripts cannot use the same concurrent location
                Device.locks[location].acquire()

                script_data = []
                    # collect data from current neighbours
                for device in self.device.neighbours:
                    data = device.get_data(location)
                    if data is not None:
                        script_data.append(data)
                # add our data, if any
                data = self.device.get_data(location)
                if data is not None:
                    script_data.append(data)

                if script_data != []:
                    # run script on data
                    result = script.run(script_data)

                    # update data of neighbours
                    for device in self.device.neighbours:
                        device.set_data(location, result)
                    # update our data
                    self.device.set_data(location, result)

                Device.locks[location].release()

            #threds wait
            self.device.bar_thr.wait()
            #reset for every round
            if self.first == 1:
                self.device.event_neighbours.clear()
                self.device.timepoint_done.clear()
            self.device.bar_thr.wait()
            #devices wait
            if self.first == 1:
                Device.bariera_devices.wait()


