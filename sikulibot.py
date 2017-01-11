import os
import datetime as dt
import subprocess
import sys
import shutil
import stat
from github import Github
from shutil import copyfile

INSTALLERS_PATH = 'Y:\Shared\Scratch\_Autobuild\Insight'
TEST_LOG_PATH = 'E:\SikuliTestLogs'
SIKULI_TESTS_FOLDER = 'TestSikuli'
WORKSPACE_PATH = 'E:\workspace'
SSH_HOME = 'E:/application/github' # location of git hub ssh key (no passphrase)
TODAY_00H00 = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


#------------------------------------------------------------------------------
def findFilesModifiedToday(path):
    file_list = []
    
    file_list_temp = os.listdir(path)
    
    for file_name in file_list_temp:
    
        full_path = os.path.join(path, file_name)
        file_stats = os.stat(full_path)
        last_mod_time = dt.datetime.fromtimestamp(file_stats.st_mtime)

        if last_mod_time > TODAY_00H00:
            file_list.append(file_name)
    
    return file_list


#------------------------------------------------------------------------------
def findTodaysInstallers():
    file_list = []

    file_list_temp = findFilesModifiedToday(INSTALLERS_PATH)
    
    for file_name in file_list_temp:
    
        file_name = file_name.lower()
        if file_name.startswith('geoscience analyst_') and \
           file_name.endswith('_setup.exe') and \
           'patch' in file_name: # only patch installers
           
           file_list.append(file_name)
    
    return file_list

    
#------------------------------------------------------------------------------
def findTodaysLogs():
    file_list = []
    
    file_list_temp = findFilesModifiedToday(TEST_LOG_PATH)
    for file_name in file_list_temp:
    
        file_name = file_name.lower()
        if file_name.startswith('geoscience analyst_') and \
           file_name.endswith('_setup.txt') and \
           'patch' in file_name: # only patch installers
           
           file_list.append(file_name)
    
    return file_list
    
    
#------------------------------------------------------------------------------
def clearPastDaysLogs():
    if not os.path.isdir(TEST_LOG_PATH):
        os.makedirs(TEST_LOG_PATH)

    file_list_temp = os.listdir(TEST_LOG_PATH)
    for file_name in file_list_temp:
    
        full_path = os.path.join(TEST_LOG_PATH, file_name)
        file_stats = os.stat(full_path)
        last_mod_time = dt.datetime.fromtimestamp(file_stats.st_mtime)

        if last_mod_time < TODAY_00H00:
            os.remove(full_path)


#------------------------------------------------------------------------------
def filenameWithoutExtension(filename):
    return os.path.splitext(filename)[0]

#------------------------------------------------------------------------------
def getBuildName(installer_name):
    return filenameWithoutExtension(installer_name)
    
#------------------------------------------------------------------------------
def findFirstUntestedInstaller():

    # list today's new Analyst installers
    installers = findTodaysInstallers()
    
    # list today's logs
    clearPastDaysLogs()
    logs = findTodaysLogs()

    for installer in installers:
        build_name = getBuildName(installer)
    
        found = False
    
        for log in logs:
            if(log.startswith(build_name)):
                found = True
                break
                
        if found == False:
            return installer
            
    return ''

#------------------------------------------------------------------------------
def getBranchName(installer_name):
    prefix = 'Geoscience ANALYST_v2.30_x64_'
    suffix = '_patch_2016-11-24-16-29_setup.exe'
    branch_name = installer_name[len(prefix):]
    branch_name = branch_name[:-len(suffix)]
    return branch_name

#------------------------------------------------------------------------------
def getRemoteNameAndSha(branch_name):
    
    personal_access_token = open('token.txt').read()   
    g = Github(personal_access_token)
    repo = g.get_repo('MiraGeoscience/InSight')
    pull_requests = repo.get_pulls()
    for pr in pull_requests:
        head = pr.head
        if branch_name in head.label:
            return head.repo.full_name, head.sha # repo name + commit id
            
    return 'MiraGeoscience/InSight', 'development'

#------------------------------------------------------------------------------
def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

#------------------------------------------------------------------------------
def getSources(remote_name, sha, dest_path):
    
    # clean up workspace
    if os.path.isdir(dest_path):
        shutil.rmtree(dest_path, onerror=remove_readonly)

    os.makedirs(dest_path)
    
    # set location of ssh key (no passphrase)
    os.environ['HOME'] = SSH_HOME
        
    # clone repo
    clone_url = 'git@github.com:' + remote_name
    res = subprocess.call(["git", "clone", clone_url, dest_path])
    if res is not 0:
        print('Failed to clone ' + remote_name)
        exit(res)
    
    # checkout branch
    res = subprocess.call(["git", \
                           "--git-dir=" + dest_path + "/.git", \
                           "--work-tree=" + dest_path, \
                           "checkout", \
                           sha, \
                           "--quiet"])

    if res is not 0:
        print('Failed to checkout branch ' + remote_name + ':' + remote_name)
        exit(res)

#------------------------------------------------------------------------------
def touch(path):
    # create an empty file
    with open(path, 'a'):
        # update mtime in case it exists
        os.utime(path, None)
        
#------------------------------------------------------------------------------
def saveLog(path, installer_name):

    log_file = path + '/log.txt'
    saved_log_file = TEST_LOG_PATH + '/' + getBuildName(installer_name) + '.txt'
    
    if os.path.exists(log_file):
        copyfile(log_file, saved_log_file)
    else:
        touch(saved_log_file)

#------------------------------------------------------------------------------
def sendZulipMessage(msg):
    res = subprocess.call(['curl', 'https://mirageoscience.zulipchat.com/api/v1/messages',\
                           '-u', 'sikuli-bot@mirageoscience.com:ALN1a7zbntcth8brlQXGAsccEQ3Bt9dE',\
                           '-d', 'type=stream',\
                           '-d', 'to=Sikuli',\
                           '-d', 'subject=QtSight',\
                           '-d', 'content=' + msg])

#------------------------------------------------------------------------------
# find first untested build (it has no test log)
installer_to_test = findFirstUntestedInstaller()

if len(installer_to_test) == 0:
    print('No new installer today')
    exit(0)

# identify repository and branch
branch_name = getBranchName(installer_to_test)
remote_name, sha = getRemoteNameAndSha(branch_name)

# get source code
print('Checking out ' + remote_name + ':' + branch_name + '...')
getSources(remote_name, sha, WORKSPACE_PATH)
    
# install Analyst via setup.exe
print('Installing ' + installer_to_test + '...')
installer_full_path = os.path.join(INSTALLERS_PATH, installer_to_test)
res = subprocess.run([installer_full_path, '/SILENT'])

if res.returncode == 0:
    print('Installed successfuly')
else:
    print('Failed to install')
    exit(1)
    
# run sikuli tests
os.environ['ANALYST_PATH'] = 'C:/Program Files/Mira Geoscience/Geoscience ANALYST'
sikuli_tests_path = WORKSPACE_PATH + '/' + SIKULI_TESTS_FOLDER

if not os.path.isdir(sikuli_tests_path):
    print('No Sikuli tests found on this branch')
    saveLog(sikuli_tests_path, installer_to_test)
    exit(0)
    
sys.path.append(sikuli_tests_path)
import RunAllTests
        
# save a copy of sikuli test log, so we know what build we tested
saveLog(sikuli_tests_path, installer_to_test)

# write a message to zulip about test result
if os.environ.get('TEST_SUCCESS') == 'TRUE':
    sendZulipMessage(installer_to_test + "\nSuccess :heavy_check_mark:")
else:
    message = installer_to_test + "\nFAILURE :x:"
    fail_list = os.environ.get('FAIL_LIST').split(';')
    
    for filename in fail_list:
        message += '\n' + filename
        
    sendZulipMessage(message)
