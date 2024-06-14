# brunch test

#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File        :   main_entrance.py
@Create Time :   2022/09/02
@Description :   标准化执行入口
"""
import os
import argparse
import sys
import re
import time
import shutil
import platform
import logging.config
import subprocess
import pymongo
import requests
import jenkins
import json
import zipfile

FIXED_REQS = "pytest==6.2.4 allure-pytest==2.8.6"
DYNA_REQS = "sdet_detection==0.4.9 increment==0.3.11.8 " \
            "pytest-sdet-case==0.6.10 pytest-sdet-xdist==1.5.0 pytest-sdet-sync==0.4.5"
PLATFORM = platform.system()
LOG_CONF = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d]%(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join("main_entrance.log"),
            'mode': 'w',
            'formatter': 'simple',
            'encoding': 'GBK',
        },
    },
    'loggers': {
        'both': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': False
        },
    },
}
MONGO_CONF = {
    "host": "10.30.6.61",
    "port": 17017,
    "db": "coverage",
    "user": "coverage",
    "password": "coverage2022",
    "table": "diff",
}
test = 'test'

logging.config.dictConfig(LOG_CONF)
LOGGER = logging.getLogger("both")

if PLATFORM.lower() == "windows":
    VENV_BASE = r"D:\venv"  # 虚拟环境统一管理根目录
    INSTALL_BASE = r"D:\Program Files"  # python解释器统一安装根目录；不同版本安装在对应版本的文件夹下，如：Python27，Python36
    SEPARATOR = "\\"
    LINE_SEPARATOR = "\r\n"
else:
    VENV_BASE = "/".join(os.getenv("MAINENTRACE").split("/")[:-1]) + "/venv"     # venv与入口代码为同级目录，先去上一级，然后获取venv目录
    INSTALL_BASE = "/usr/local"
    SEPARATOR = "/"
    LINE_SEPARATOR = "\n"
    EXECUTABLE_BASE = "/bin/bash"


def _wait_until_keywords_success(keywords, timeout=360, period=0.1, **args):
    end = time.time() + timeout
    LOGGER.info(f"等待方法返回值")
    while time.time() < end:
        result = keywords(**args)
        if result:
            return result
        time.sleep(period)
    return False


def _write_file(file, info):
    if os.path.exists(file):
        os.remove(file)
    with open(file, 'w', encoding='utf-8') as f:
        f.write(info)


def _execute_cmd(cmd):
    LOGGER.debug(cmd)
    if PLATFORM.lower() == 'linux':
        res = subprocess.run(cmd, shell=True, executable='/bin/bash', stderr=subprocess.PIPE)
        LOGGER.info("执行命令完成：returncode：{}，stderr：{}".format(res.returncode, res.stderr))
    else:
        os.system(cmd)


def _read_file(file, encoding='utf-8'):
    if not os.path.exists(file):
        raise Exception(f"文件{file}不存在")
    with open(file, 'r', encoding=encoding) as f:
        return f.read()


def db_select(table, cond):
    client = pymongo.MongoClient(host=MONGO_CONF["host"],
                                 port=MONGO_CONF["port"])
    db = client[MONGO_CONF["db"]]
    db.authenticate(MONGO_CONF["user"],
                    MONGO_CONF["password"])
    target = db[table]
    data = target.find_one(cond)
    return data


class VenvManager:
    def __init__(self, venv_name, python_version):
        """
        :param venv_name: 虚拟环境名称
        :param python_version: python版本，如：2.7，3.6等
        :return:
        """
        VenvManager.venv_name = venv_name
        VenvManager.venv_path = os.path.join(VENV_BASE, venv_name)  # 获取对应虚拟环境路径
        if os.getenv("MAINENTRACE") == "/sdet/standard_execution":
            version_folder = "python" + python_version
        else:
            version_folder = "Python" + python_version.replace(".", "")
        python_path = os.path.join(INSTALL_BASE, version_folder)  # 获取对应python版本的python安装目录
        if platform.system().lower() == "windows":
            VenvManager.python_exe = os.path.join(VenvManager.venv_path, "Scripts", "python.exe")
            VenvManager.venv_exe = os.path.join(python_path, "Scripts", "virtualenv.exe")
            VenvManager.active_script = os.path.join(VenvManager.venv_path, "Scripts", "activate")
            VenvManager.active_py = os.path.join(VenvManager.venv_path, "Scripts", "activate_this.py")
            VenvManager.site_packages = os.path.join(VenvManager.venv_path, "Lib", "site-packages")
        else:
            VenvManager.python_exe = os.path.join(VenvManager.venv_path, "bin", "python")
            VenvManager.venv_exe = os.path.join(python_path, "bin", "virtualenv")
            VenvManager.active_script = "source " + os.path.join(VenvManager.venv_path, "bin", "activate")
            VenvManager.active_py = os.path.join(VenvManager.venv_path, "bin", "activate_this.py")
            VenvManager.site_packages = os.path.join(VenvManager.venv_path, "lib", "python" + python_version, "site-packages")

    @staticmethod
    def manage_venv():
        """虚拟环境管理，如果实例化对应名称的虚拟环境存在，则返回；如果不存在，则创建对应名称，对应版本的python虚拟环境
        """
        if os.path.exists(VenvManager.venv_path):
            LOGGER.info("虚拟环境：{0}已存在".format(VenvManager.venv_name))
        else:
            # 创建虚拟环境
            cmd = 'cd {0} && "{1}" {2}'.format(VENV_BASE, VenvManager.venv_exe, VenvManager.venv_name)
            _execute_cmd(cmd)
            LOGGER.info("成功创建虚拟环境：{0}".format(VenvManager.venv_name))

            cmd = '{0} && pip install {1}'.format(VenvManager.active_script, FIXED_REQS)
            _execute_cmd(cmd)

    @staticmethod
    def install_dyna_reqs():
        """在虚拟环境中安装更新需要更新的依赖包"""
        cmd = '{0} && pip install -U {1}'.format(VenvManager.active_script, DYNA_REQS)
        _execute_cmd(cmd)

    @staticmethod
    def install_requirements(req_file=None):
        """在虚拟环境中安装对应版本python指定的pytest+allure，安装req_file中的依赖包
        :param req_file: 依赖文件的requirements.txt文件的全路径
        """
        if req_file:
            # 安装或更新对应的依赖包
            cmd = '{0} && pip install -U -r "{1}"'.format(VenvManager.active_script, req_file)
            _execute_cmd(cmd)


class JenkinsProvider:
    username = "autotest"
    token = "1118af81829932afb526396ad49cd80ac1"

    def __init__(self, workspace, build_url):
        """
        :param workspace: 工作空间
        :param build_url: 构建url
            例： http://ta.sdet.cloud/job/lq/job/LQ_DAILY_RERUN/124/
        :return:
        """
        JenkinsProvider.workspace = workspace
        JenkinsProvider.workspace_url = "/".join(build_url.split("/")[0:-2]) + "/ws"
        info = build_url.split("//")[-1].split("/")
        JenkinsProvider.build_number = int(info[-2])
        JenkinsProvider.jenkins_base = "http://" + info[0]
        JenkinsProvider.job_full_name = "/".join(info[2:-1:2])
        JenkinsProvider.server = jenkins.Jenkins(JenkinsProvider.jenkins_base,
                                                 username=JenkinsProvider.username,
                                                 password=JenkinsProvider.token)


class CaseRunner:
    last_failed_file = "lastfailed"
    latest_file = "latest"
    rerun_file = "rerun.py"
    case_filter_file = "autoid_csv"
    fail_count = -1

    def _rerun_args_parse(self, args):
        """rerun 参数处理，去除main run参数中的并发处理，去除main run中的-m参数
        """
        out = os.getenv("pytest_args_rerun", None)
        if out not in [None, ""]:
            return out
        temp = args.split(" ")
        if "/" in temp[0] or "\\" in temp[0]:
            args = " ".join(temp[1:])    # 去除重跑中的目录，重跑通过nodeids指定用例，无需目录
        pattern = re.compile('-m( |=)(\"|\')(.*)(\"|\')')
        out = re.sub(pattern, '', args)  # rerun去除main run参数中的-m=""或-m ""或-m=''或 -m ''参数处理

        # rerun去除main run参数中的自定义参数筛选参数处理
        pattern = re.compile('-M( |=)\S+')
        out = re.sub(pattern, '', out)
        pattern = re.compile('-P( |=)\S+')
        out = re.sub(pattern, '', out)
        pattern = re.compile('-A( |=)\S+')
        out = re.sub(pattern, '', out)
        pattern = re.compile('-F( |=)\S+')
        out = re.sub(pattern, '', out)
        return out

    def _get_file_path_and_class(self, class_name):
        full_class_name = class_name.split(".")
        file_path = "/".join(full_class_name[0:-1]) + ".py"
        class_name = full_class_name[-1]
        return file_path, class_name

    def _get_rerun_base(self, rerun_base_job, rerun_base_build_number):
        """rerun job 信息的默认值处理，获取处理后的rerun_base_job，rerun_base_build_number
        :return:rerun_base_job, rerun_base_build_number
        """
        # rerun_base_job为空，则认为rerun_base_job为当前rerun job 的main job
        if rerun_base_job == "" or rerun_base_job == JenkinsProvider.job_full_name[:-6]:
            rerun_base_job = JenkinsProvider.job_full_name[:-6]  # 获取当前rerun job 的main job
            if rerun_base_build_number == "":
                rerun_base_build_number = self._get_latest_build_number(rerun_base_job)  # 获取main job的最新一次构建号
        elif rerun_base_job == JenkinsProvider.job_full_name:
            # 如果重跑的构建号为空，则默认为当前rerun job本次构建号减1
            if rerun_base_build_number == "":
                rerun_base_build_number = JenkinsProvider.build_number - 1
        else:
            raise Exception("rerun_base_job有误，不支持main job和rerun job之外的job作为rerun base job")

        rerun_base_build_number = int(rerun_base_build_number)
        LOGGER.info("重跑base job：{}，base build number：{}".format(rerun_base_job, rerun_base_build_number))
        return rerun_base_job, rerun_base_build_number

    @staticmethod
    def _get_jenkins_report(rerun_base_job, rerun_base_build_number, data_test):
        result = JenkinsProvider.server.get_build_test_report(rerun_base_job, rerun_base_build_number)
        return result, data_test

    def _get_failed_cases(self, rerun_base_job, rerun_base_build_number):
        """
        :param rerun_base_job: 重跑base job，即基于哪个job重跑；注意：为jenkins的full job name，例：TA-Sample/TA-Sample-Main
        :param rerun_base_build_number: 重跑base job的构建号，即基于该job的哪次构建号重跑
        :return:
        """
        result = _wait_until_keywords_success(self._get_jenkins_report,
                                              rerun_base_job=rerun_base_job,
                                              rerun_base_build_number=rerun_base_build_number)
        if result is False:
            raise TimeoutError("获取rerun base job test report 失败，报告未生成")

        cases = result.get("suites")[0].get("cases")
        failed_cases = []
        for case in cases:
            if case.get("status") not in ["PASSED", "FIXED", "SKIPPED"]:
                file_path, class_name = self._get_file_path_and_class(case.get("className"))
                case_name = case.get("name")
                nodeid = file_path + "::" + class_name + "::" + case_name
                if not nodeid.startswith('.py'):
                    failed_cases.append(nodeid)
        if not failed_cases:
            CaseRunner.fail_count = 0
            return None
        CaseRunner.fail_count = len(failed_cases)
        LOGGER.info("成功获取base job：{}第{}次构建失败用例，共{}个".format(rerun_base_job, rerun_base_build_number, CaseRunner.fail_count))
        info = "\n".join(failed_cases)
        file = os.path.join(os.getcwd(), CaseRunner.last_failed_file)
        _write_file(file, info)
        return failed_cases

    @staticmethod
    def _get_cmdenv(args):
        pattern = "--cmdenv( +)\S+"
        out = re.search(pattern, args)
        if out is not None:
            return out.group()
        else:
            return ""

    @staticmethod
    def _get_latest_cases(args):
        cmdenv = CaseRunner._get_cmdenv(args)
        cmd = f'{VenvManager.active_script} && pytest --collect-only {cmdenv} -q --disable-warnings >> {CaseRunner.latest_file}'
        LOGGER.info("重新采集用例，以过滤重命名或删除文件")
        _execute_cmd(cmd)
        try:
            latest_cases = _read_file(CaseRunner.latest_file, "gbk").split(f"\n\n")[0].split("\n")     # 去除collect最后总数的输出
        except:
            LOGGER.info(f"重新采集用例失败，详见：{JenkinsProvider.workspace_url}/{CaseRunner.latest_file}/*view*/")
            latest_cases = None
        return latest_cases

    @staticmethod
    def _get_latest_build_number(job_name):
        result = JenkinsProvider.server.get_job_info(job_name)
        return result['lastBuild']['number']

    def _main_run(self, args):
        if os.getenv(CaseRunner.case_filter_file, None) not in [None, ""]:
            args += f" -F={CaseRunner.case_filter_file}"
        LOGGER.info(os.getenv(CaseRunner.case_filter_file, None))
        cmd = '{0} && pytest {1} --alluredir=allure-results --junit-xml=report.xml'.format(VenvManager.active_script, args)
        _execute_cmd(cmd)

    def _rerun(self, failed_cases, args):
        exec(open(VenvManager.active_py).read(), dict(__file__=VenvManager.active_py))
        pytest_args = failed_cases
        pytest_args.extend(args.split())
        pytest_args.append("--continue-on-collection-errors")
        pytest_args.append("--alluredir=allure-results")
        pytest_args.append("--junit-xml=report.xml")
        info = """import pytest\npytest.main({0})""".format(pytest_args)
        file = os.path.join(os.getcwd(), CaseRunner.rerun_file)
        _write_file(file, info)
        cmd = '{0} {1}'.format(VenvManager.python_exe, file)
        _execute_cmd(cmd)

    def case_runner(self, args, rerun, rerun_base_job, rerun_base_build_number):
        if rerun == "false":
            LOGGER.info("主构建开始")
            self._main_run(args)
        else:
            LOGGER.info("重跑开始")
            # 默认值处理，获取处理后的rerun_base_job，rerun_base_build_number
            rerun_base_job, rerun_base_build_number = self._get_rerun_base(rerun_base_job, rerun_base_build_number)
            # 获取rerun base job指定构建号的失败用例
            failed_cases = self._get_failed_cases(rerun_base_job, rerun_base_build_number)
            if failed_cases in [None, []]:
                LOGGER.info("无失败脚本，跳过rerun")
                return
            LOGGER.debug(f"本次执行失败脚本: {failed_cases}")

            args = self._rerun_args_parse(args)
            latest_cases = self._get_latest_cases(args)
            LOGGER.debug(f"本次重新采集脚本: {latest_cases}")
            rerun_cases = [case for case in failed_cases if case in latest_cases]
            delete_cases = [case for case in failed_cases if case not in rerun_cases]

            LOGGER.info(f"本次执行删除或重命名脚本共{len(delete_cases)}个")
            LOGGER.debug(f"本次执行删除或重命名脚本: {delete_cases}")
            LOGGER.info(f"重新计算后本次待执行脚本共{len(rerun_cases)}个")

            if rerun_cases in [None, []]:
                LOGGER.info("跳过rerun")
                return
            self._rerun(rerun_cases, args)


class TADC:
    tadc_base = "http://aladdin-tadc.rd.800best.com/openapi/aladdintadc/notify"

    def tadc_notify(self, project_name, activity_name, purpose, jira, test_version, test_branch, category, username,
                    qas_module_list, auto_ta_plan, run_type):
        if auto_ta_plan == "true":
            auto_ta_plan = True
        data = {
            'projectName': project_name,
            'projectId': None,
            'activityName': activity_name,
            'purpose': purpose,
            'jira': jira,
            'testVersion': test_version,
            'testBranch': test_branch,
            'jenkinsUrl': JenkinsProvider.jenkins_base.split("//")[-1],
            'fullJobName': JenkinsProvider.job_full_name,
            'buildNum': JenkinsProvider.build_number,
            'category': category,
            'userName': username,
            'qasModuleList': qas_module_list,
            'autoTaPlan': auto_ta_plan,
            'runType': run_type
        }
        headers = {'content-type': 'application/json'}
        LOGGER.debug(data)
        result = requests.get(TADC.tadc_base, params=data, headers=headers, timeout=3600)
        LOGGER.info("触发TADC notify, status_code:{}".format(result.status_code))


class Coverage:
    storage_base = "http://blob.sdet.cloud/repository/classes/war"
    target_gz_name = "classfiles.tar.gz"
    target_file_dir = "classfiles"
    jar_path = os.path.join(INSTALL_BASE, "jacoco-0.8.7.1", "lib", "jacococli.jar")

    def coverage_execute(self, addresses, job_path, download_path, filter_prefix, git_url, base_vsn, now_vsn, project_name, version, key):
        # 调用增量计算方法
        try:
            cmd = f"{VenvManager.active_script} && python -m increment.jacoco_increment '{git_url}' '{base_vsn}' '{now_vsn}' '{key}'"
            _execute_cmd(cmd)
        except Exception as e:
            LOGGER.info(f"执行increment.jacoco_increment发生异常，原因：{e}")
        try:
            cmd = f"{VenvManager.active_script} && python -m increment.jar_manage '{download_path}' '{filter_prefix}' '{JenkinsProvider.workspace}'"
            _execute_cmd(cmd)
        except Exception as e:
            LOGGER.info(f"执行increment.jar_manager发生异常，原因：{e}")
        # 执行数据收集与合并

        target_exec_paths = []
        info = addresses.split(":")
        ip, port = info[0], info[1]
        exec_path = os.path.join(job_path, "all.exec")
        try:
            cmd = 'java -jar "{}" dump --address {} --port {} --destfile {}'.format(self.jar_path, ip, port, exec_path)
            target_exec_paths.append(exec_path)
            _execute_cmd(cmd)
        except Exception as e:
            LOGGER.info(f"执行dump发生异常，原因：{e}")

        increment_data = _wait_until_keywords_success(db_select, table=MONGO_CONF["table"], cond={"name": key}).get("key", [])
        if increment_data:
            LOGGER.info(f"成功获取mongodb数据，key：{key}，并写入文件")
            increment_data_file_path = os.path.join(job_path,"increment_data_file")
            increment_data_json = json.dumps(increment_data, ensure_ascii=False)
            _write_file(increment_data_file_path, increment_data_json)
            LOGGER.info("开始report")
            class_files_path = os.path.join(JenkinsProvider.workspace, "classfiles")
            increment_report_path = os.path.join(job_path, "increment_report")
            # os.makedirs(increment_report_path)
            source_files_paths = self.get_remote_source_files(git_url=git_url, now_vsn=now_vsn, target_dir=JenkinsProvider.workspace)
            tmp = []
            for source_file in source_files_paths:
                tmp.append(f'--sourcefiles "{source_file}"')
            cmd = f'java -jar "{self.jar_path}" report "{exec_path}" --classfiles "{class_files_path}" ' + ' '.join(tmp) + f' --diffCodeFiles "{increment_data_file_path}" --html "{increment_report_path}"'
            file = os.path.join(os.getcwd(), 'coverage_report.sh')
            _write_file(file, cmd)
            subprocess.run(f"sh {file}", shell=True, executable='/bin/bash')

            LOGGER.info("结束report")
            # LOGGER.info("开始打包报告")
            # cmd = 'zip -r report.zip increment_report'
            # _execute_cmd(cmd)
            # LOGGER.info("报告打包完成")

            LOGGER.info("开始进行:增量代码覆盖率数据上传至fast测试平台")
            try:
                job_name = key.split('-')[0].split('/')[-1]
                cmd = f"{VenvManager.active_script} && python -m increment.cov_report '{increment_report_path}' '{job_name}' '{project_name}' '{version}' '{base_vsn}' '{now_vsn}' '{ip}'"
                _execute_cmd(cmd)
            except Exception as e:
                LOGGER.info(f"执行increment.cov_report发生异常，原因：{e}")
            LOGGER.info("完成:增量代码覆盖率数据上传至fast测试平台")
        else:
            LOGGER.info("无增量代码数据,不统计增量代码覆盖率.")
        self.sync_coverage()

    def get_remote_source_files(self, git_url, now_vsn, target_dir):
        """
        获取源码,用于覆盖率报告生成代码染色图
        """
        git_repo_name = git_url.split("/")[-1].split(".git")[0]
        # 10.30.6.52 为hx-coverage-2机器ip地址,7887为SimpleHTTPServer端口
        remote_file_url = f"http://10.30.6.52:7887/{git_repo_name}/{now_vsn}.zip"
        LOGGER.info(f"开始进行:获取源码{remote_file_url}")
        local_zip_file_path = os.path.join(target_dir, remote_file_url.split("/")[-1])
        local_source_file_dir = os.path.join(target_dir, remote_file_url.split("/")[-1].split(".zip")[0])
        response = requests.get(url=remote_file_url, stream=True)
        LOGGER.info(f"获取源码{remote_file_url},响应{response.status_code}")
        with open(local_zip_file_path, "wb") as f:
            for bl in response.iter_content(chunk_size=1024):
                if bl:
                    f.write(bl)
        LOGGER.info("完成:源码获取")
        LOGGER.info(f"开始进行:源码zip文件解压至{local_source_file_dir}")
        f = zipfile.ZipFile(local_zip_file_path)
        f.extractall(local_source_file_dir, f.namelist())
        LOGGER.info("完成:源码zip文件解压")
        source_files = []
        for root, dirs, files in os.walk(local_source_file_dir, topdown=True):
            for name in dirs:
                if name in ["java"] and not root.endswith("test"):
                    source_files.append(os.path.join(root, name))
                    break
        return source_files

    def sync_coverage(self):
        info = f"""if __name__ == "__main__":\n    from sdet_sync.pytest_sdet_sync import sdet_sync_coverage\n    print(sdet_sync_coverage())\n"""
        py_file = os.path.join(os.getcwd(), 'sync_coverage.py')
        _write_file(py_file, info)

        cmd = '{0} {1}'.format(VenvManager.python_exe, py_file)
        LOGGER.info(cmd)
        try:
            subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
        except Exception as e:
            LOGGER.info(f"执行上传覆盖率发生异常，原因：{e}")
        finally:
            if os.path.exists(os.path.join(VenvManager.site_packages, "sdet_sync", "logs")):
                shutil.copytree(os.path.join(VenvManager.site_packages, "sdet_sync", "logs"),
                                os.path.join(os.getcwd(), "sync_logs"), dirs_exist_ok=True)
                LOGGER.info(f"上传覆盖率日志，地址：{JenkinsProvider.workspace_url + '/sync_logs/default_info.logs/*view*/'}")
            else:
                LOGGER.debug(f"无上传日志")


class HealthyCheck:
    @staticmethod
    def get_detection_yaml():
        path = None
        for root, dirs, files in os.walk("."):
            for file in files:
                if 'healthy_check.yaml' in file:
                    path = os.path.join(os.path.abspath(os.path.curdir), os.path.join(root, file)[2:])
        return path

    @staticmethod
    def healthy_check_execute(file):
        LOGGER.info(f"检测配置文件路径：{file}")
        exec(open(VenvManager.active_py).read(), dict(__file__=VenvManager.active_py))

        info = f"""if __name__ == "__main__":\n    from sdet_detection.detection import healthy_ck\n    print(healthy_ck(r'{file}'))\n"""
        py_file = os.path.join(os.getcwd(), 'healthy_check.py')
        _write_file(py_file, info)

        cmd = '{0} {1}'.format(VenvManager.python_exe, py_file)
        LOGGER.info(cmd)

        try:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
            LOGGER.debug(f"初始化检测返回内容：{res.stdout}")
            res_tuple = tuple(eval(str(res.stdout.split(str.encode(f'{LINE_SEPARATOR}'))[-2], encoding='gbk')))
            hc_result = res_tuple[0]
            LOGGER.info(f"环境检测结果: {res_tuple[0]}")
            LOGGER.info(f"环境检测未通过项: {res_tuple[2]}")
            LOGGER.info(f"环境检测过程异常信息: {res_tuple[3]}")
        except Exception as e:
            hc_result = "error"
            LOGGER.info(f"环境检测结果: {hc_result}")
            LOGGER.info(f"环境检测发生异常，异常详情：{e}")
        finally:
            if os.path.exists(os.path.join(VenvManager.site_packages, "sdet_detection", "logs")):
                shutil.copytree(os.path.join(VenvManager.site_packages, "sdet_detection", "logs"),
                                os.path.join(os.getcwd(), "detection_logs"), dirs_exist_ok=True)
                LOGGER.info(f"环境检测详细日志，地址：{JenkinsProvider.workspace_url + '/detection_logs/default_info.logs/*view*/'}")
            else:
                LOGGER.debug(f"无环境检测日志")
        return hc_result


class MainEntrance:

    def __init__(self, args):
        self.args = args
        LOGGER.info("执行命令：{0}".format(self.args))
        JenkinsProvider(self.args.workspace, self.args.build_url)

    def manage_venv(self):
        args = self.args
        workspace = args.workspace.split(SEPARATOR)
        if args.venv_by_folder == "true":
            venv_name = workspace[-2]
        else:
            venv_name = workspace[-1]
            if args.rerun == "true":
                venv_name = venv_name[:-6]

        venv = VenvManager(venv_name, args.python_version)

        if args.clean_venv == "true":
            if os.path.exists(VenvManager.venv_path):
                shutil.rmtree(VenvManager.venv_path)
                LOGGER.info("成功删除已有虚拟环境：{0}".format(VenvManager.venv_name))

        venv.manage_venv()
        if os.path.exists(os.path.join(args.workspace, "requirements.txt")):
            venv.install_requirements(os.path.join(args.workspace, "requirements.txt"))
        venv.install_dyna_reqs()

    def run(self):
        args = self.args
        runner = CaseRunner()
        runner.case_runner(args.pytest_args, args.rerun, args.rerun_base_job, args.rerun_base_build_number)

    def tadc_notify(self):
        if os.path.exists(os.path.join(VenvManager.site_packages, "sdet_sync")):
            shutil.copytree(os.path.join(VenvManager.site_packages, "sdet_sync", "logs"),
                            os.path.join(os.getcwd(), "sync_logs"), dirs_exist_ok=True)
            LOGGER.info("*******************************************实时结果上传结束********************************************")
            LOGGER.info(f"实时结果上传详细日志，地址：{JenkinsProvider.workspace_url + '/sync_logs/default_info.logs/*view*/'}")
        else:
            LOGGER.info("*******************************************开始上传数据中心********************************************")
            args = self.args
            if args.tadc_notify == "true" and CaseRunner.fail_count != 0:
                tadc = TADC()
                tadc.tadc_notify(args.project_name, args.activity_name, args.purpose,
                                 args.jira, args.test_version, args.test_branch, args.category, args.build_user_id.upper(),
                                 args.qas_module_list, args.auto_ta_plan, args.run_type)

    def coverage_report(self):
        args = self.args
        if args.auto_coverage == 'true':
            LOGGER.info("*******************************************开始执行覆盖率统计********************************************")
            Coverage().coverage_execute(args.project_server, args.workspace, args.download_path, args.filter_prefix,
                                        args.git_url, args.base_vsn, args.now_vsn, args.project_name, args.test_version,
                                        JenkinsProvider.job_full_name + "-" + str(JenkinsProvider.build_number))
        else:
            LOGGER.info("*******************************************不进行覆盖率统计********************************************")

    def healthy_check(self):
        file = HealthyCheck.get_detection_yaml()
        hc_result = "success"
        if file is None:
            LOGGER.info("无检测文件，跳过检测")
        else:
            hc_result = HealthyCheck.healthy_check_execute(file)
        return hc_result


def debug_init():
    os.environ['WORKSPACE'] = r"D:\Jenkins\workspace\lq\LQ_DAILY"
    os.environ['python_version'] = "3.9"
    os.environ['venv_by_folder'] = "true"
    os.environ['clean_venv'] = "false"
    os.environ['rerun_base_job'] = ""
    os.environ['rerun_base_build_number'] = ""
    os.environ['pytest_args'] = " "
    os.environ['tadc_notify'] = "false"
    os.environ['project_name'] = "项目名称"
    os.environ['activity_name'] = "活动名称"
    os.environ['category'] = "API"
    os.environ['BUILD_URL'] = "http://ta.sdet.cloud/job/TA-Sample/job/TA-Sample-Main_Rerun/387/"
    os.environ['jira'] = ""
    os.environ['purpose'] = ""
    os.environ['test_version'] = ""
    os.environ['test_branch'] = ""
    os.environ['BUILD_USER_ID'] = "bg276635"
    os.environ['qas_module_list'] = "来取:系统用例:来取自动化"
    os.environ['run_type'] = "回归测试"


def get_os_env_args():
    env_list = [
        'WORKSPACE', 'BUILD_URL', 'BUILD_USER_ID',
        'python_version', 'venv_by_folder', 'clean_venv',
        'rerun_base_job', 'rerun_base_build_number', 'pytest_args',
        'tadc_notify', 'project_name', 'activity_name', 'category', 'jira', 'purpose', 'test_version', 'test_branch',
        'auto_ta_plan', 'run_type']

    args = argparse.Namespace()

    if 'rerun' in os.environ.get('WORKSPACE', None).lower():
        args.__setattr__('rerun', 'true')
        LOGGER.debug("set rerun: true")
    else:
        args.__setattr__('rerun', 'false')
        LOGGER.debug("set rerun: false")

    if os.environ.get('qas_module_list', None) not in [None, ""]:
        args.__setattr__('qas_module_list', os.environ.get('qas_module_list', None).strip(" "))
        LOGGER.debug("set qas_module_list: " + os.environ.get('qas_module_list', None).strip(" "))
    if os.environ.get('qasModuleList', None) not in [None, ""]:
        args.__setattr__('qas_module_list', os.environ.get('qasModuleList', None).strip(" "))
        LOGGER.debug("set qas_module_list: " + os.environ.get('qasModuleList', None).strip(" "))

    for key in env_list:
        if os.environ.get(key, None) not in [None, ""]:
            value = os.environ.get(key, None).strip(" ")
            if value != "" and value is not None:
                if value[0] == "'" or value[0] == '"':          # 去除头尾引号‘’，但不去出-m=‘a or b’这种引号
                    value = value.strip("'").strip('"')
            args.__setattr__(key.lower(), value)
            LOGGER.debug("set " + key.lower() + ": " + value)
        else:
            args.__setattr__(key.lower(), '')
            LOGGER.debug("set " + key.lower() + ": None")
    return args


def get_coverage_os_env_args():
    args = argparse.Namespace()
    env_list = [
        'WORKSPACE', 'BUILD_URL',
        'python_version', 'venv_by_folder',
        'auto_coverage', 'project_server', 'download_path', 'filter_prefix',
        'git_url', 'base_vsn', 'now_vsn',
        'project_name', 'activity_name', 'test_version', 'test_branch']

    args.__setattr__("clean_venv", "false")
    LOGGER.debug("set clean_venv: false")
    args.__setattr__("rerun", "false")
    LOGGER.debug("set rerun: false")

    for key in env_list:
        if os.environ.get(key, None) not in [None, ""]:
            value = os.environ.get(key, None).strip(" ")
            args.__setattr__(key.lower(), value)
            LOGGER.debug("set " + key.lower() + ": " + value)
        else:
            args.__setattr__(key.lower(), '')
            LOGGER.debug("set " + key.lower() + ": None")
    return args


def standard_execution_user_guide():
    LOGGER.info("""参数说明： 
    一：虚拟环境管理相关参数：
    python_version: 自动化脚本执行使用的python版本
    venv_by_folder: 是否根据文件夹名创建虚拟环境；否则根据job名创建
    clean_venv: 测试执行前是否清空虚拟环境
    
    二：测试执行相关参数：
    rerun_base_job: 重跑base job；仅rerun时需要
    rerun_base_build_number: 重跑base job的构建号；仅rerun时需要
    pytest_args: pytest参数
    
    三：通知数据中心相关参数：
    tadc_notify: 本次构建结果是否上传数据中心
    project_name: 业务系统名
    activity_name: 活动名
    category: case类型；可选[CODE, API, DESKTOP, WEB, APP, SPECIAL, category]
    jira: jira链接
    purpose: 测试目的
    test_version: 测试版本
    test_branch: 测试分支
    qas_module_list: qas用例集信息
    auto_ta_plan: 是否自动创建测试计划
    run_type: 测试阶段
    
    更多说明详见：http://wiki.rd.800best.com/pages/viewpage.action?pageId=89578868
    """)


def coverage_user_guide():
    LOGGER.info("""参数说明： 
        一：虚拟环境管理相关参数：
        python_version: 自动化脚本执行使用的python版本
        venv_by_folder: 是否根据文件夹名创建虚拟环境；否则根据job名创建
        
        二、覆盖率统计相关参数：
        auto_coverage: 是否自动生成测试覆盖率
        project_server: 项目服务器;格式ip:port，多个间采用;分隔
        
        三、上传数据中心相关参数：
        project_name: 业务系统名
        activity_name: 活动名
        test_version: 版本号
        test_branch: 测试分支
        """)


if __name__ == "__main__":
    ws = os.environ.get('WORKSPACE', None)
    if not os.path.exists(VENV_BASE):
        os.mkdir(VENV_BASE)

    if 'coverage_report' in ws.lower():
        LOGGER.info("******************************************覆盖率统计参数说明*******************************************")
        coverage_user_guide()
        args = get_coverage_os_env_args()
        me = MainEntrance(args)
        me.manage_venv()
        me.coverage_report()
    else:
        LOGGER.info("******************************************标准化执行参数说明*******************************************")
        standard_execution_user_guide()
        args = get_os_env_args()
        me = MainEntrance(args)
        LOGGER.info("*******************************************开始配置虚拟环境********************************************")
        me.manage_venv()
        LOGGER.info("*****************************************开始进行初始化环境检测****************************************")
        if me.healthy_check() in ["success", "warning"]:
            LOGGER.info("********************************************开始测试执行***********************************************")
            me.run()
            me.tadc_notify()
        else:
            sys.exit("Healthy Check Failed")
