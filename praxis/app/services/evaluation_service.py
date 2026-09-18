import os
import tarfile
import tempfile
import subprocess
import time
from dataclasses import dataclass
from typing import Optional
import logging

from app.models import Team, Bug, Level
from app.services.gitlab_service import get_latest_commit_sha, download_repository_archive

logger = logging.getLogger(__name__)

@dataclass
class EvaluationResult:
    status: str
    passed: bool
    score: int
    exit_code: Optional[int]
    stdout: str
    stderr: str
    execution_time: float
    commit_sha: Optional[str]

class EvaluationError(Exception):
    pass

def evaluate_submission(team: Team, bug: Bug, level: Level) -> EvaluationResult:
    """
    Evaluates a team's submission for a given bug.
    Supports two backends based on EVAL_BACKEND env var:
    - 'docker': Runs synchronously via subprocess (fallback for local dev)
    - 'kubernetes': Creates a K8s Job and waits for completion (production)
    """
    backend = os.getenv("EVAL_BACKEND", "docker").lower()

    if not team.gitlab_project_id:
        return _fail_result("Team does not have a GitLab repository linked.", status="error")
        
    try:
        commit_sha = get_latest_commit_sha(team.gitlab_project_id)
    except Exception as e:
        return _fail_result(f"Failed to fetch commit from GitLab: {e}", status="error")
        
    if not commit_sha:
        return _fail_result("No commits found in the repository.", status="error")

    # The official test file to run
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    official_test_path = os.path.join(project_root, "tests", "evaluation", f"level_{level.number}", f"test_bug_{bug.id}.py")
    
    if not os.path.exists(official_test_path):
        return _fail_result(f"Official test not found for level {level.number}, bug {bug.id}", status="error", commit_sha=commit_sha)

    if backend == "kubernetes":
        return _evaluate_kubernetes(team, bug, level, commit_sha, official_test_path)
    else:
        return _evaluate_docker(team, bug, level, commit_sha, project_root)

def _evaluate_docker(team: Team, bug: Bug, level: Level, commit_sha: str, project_root: str) -> EvaluationResult:
    start_time = time.time()
    
    with tempfile.TemporaryDirectory() as workspace_dir:
        archive_path = os.path.join(workspace_dir, "repo.tar.gz")
        extract_path = os.path.join(workspace_dir, "student_code")
        
        try:
            download_repository_archive(team.gitlab_project_id, commit_sha, archive_path)
        except Exception as e:
            return _fail_result(f"Failed to download repository: {e}", status="error", commit_sha=commit_sha)
            
        os.makedirs(extract_path, exist_ok=True)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=extract_path)
            extracted_dirs = os.listdir(extract_path)
            if len(extracted_dirs) == 1 and os.path.isdir(os.path.join(extract_path, extracted_dirs[0])):
                student_code_dir = os.path.join(extract_path, extracted_dirs[0])
            else:
                student_code_dir = extract_path
        except Exception as e:
            return _fail_result(f"Failed to extract repository: {e}", status="error", commit_sha=commit_sha)

        official_tests_dir = os.path.join(project_root, "tests", "evaluation", f"level_{level.number}")
        python_image = os.getenv("EVALUATOR_IMAGE", "praxis-evaluator:latest")
        
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cpus", "0.5",
            "-m", "128m",
            "--pids-limit", "50",
            "--cap-drop=ALL",
            "--read-only",
            "--tmpfs", "/tmp",
            "-v", f"{student_code_dir}:/workspace:ro",
            "-v", f"{official_tests_dir}:/tests:ro",
            python_image,
            "pytest", f"/tests/test_bug_{bug.id}.py"
        ]
        
        try:
            process = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=15.0,
                shell=False
            )
            
            execution_time = time.time() - start_time
            passed = process.returncode == 0
            
            return EvaluationResult(
                status="passed" if passed else "failed",
                passed=passed,
                score=100 if passed else 0,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                execution_time=execution_time,
                commit_sha=commit_sha
            )
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return EvaluationResult(
                status="timeout",
                passed=False,
                score=0,
                exit_code=124,
                stdout=e.stdout.decode() if e.stdout and isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode() if e.stderr and isinstance(e.stderr, bytes) else (e.stderr or "Execution timed out."),
                execution_time=execution_time,
                commit_sha=commit_sha
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return _fail_result(f"Docker execution error: {e}", status="error", commit_sha=commit_sha, exec_time=execution_time)


def _evaluate_kubernetes(team: Team, bug: Bug, level: Level, commit_sha: str, official_test_path: str) -> EvaluationResult:
    start_time = time.time()
    try:
        from kubernetes import client, config
        from kubernetes.client.rest import ApiException
    except ImportError:
        return _fail_result("Kubernetes library not installed.", status="error", commit_sha=commit_sha)

    try:
        # Works inside a pod; fallbacks could be added for local testing of K8s api
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            return _fail_result("Failed to load Kubernetes config.", status="error", commit_sha=commit_sha)

    core_v1 = client.CoreV1Api()
    batch_v1 = client.BatchV1Api()
    
    namespace = os.getenv("EVAL_NAMESPACE", "praxis")
    job_id = f"eval-{team.id}-{bug.id}-{int(time.time())}"
    configmap_name = f"{job_id}-test"
    
    # Read test file content
    with open(official_test_path, 'r') as f:
        test_code = f.read()

    # Create ConfigMap for the test file
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=configmap_name),
        data={f"test_bug_{bug.id}.py": test_code}
    )
    
    try:
        core_v1.create_namespaced_config_map(namespace=namespace, body=configmap)
    except ApiException as e:
        return _fail_result(f"Failed to create ConfigMap: {e}", status="error", commit_sha=commit_sha)

    # Prepare Job
    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
    # Using wget + tar to extract to /workspace in an initContainer
    fetch_cmd = (
        f"wget -qO- --header \"PRIVATE-TOKEN: $GITLAB_TOKEN\" "
        f"\"{gitlab_url}/api/v4/projects/{team.gitlab_project_id}/repository/archive.tar.gz?sha={commit_sha}\" | "
        f"tar -xz -C /workspace --strip-components=1"
    )

    evaluator_image = os.getenv("EVALUATOR_IMAGE", "praxis-evaluator:latest")

    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_id),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=20, # overall timeout
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "evaluator"}),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    volumes=[
                        client.V1Volume(name="workspace", empty_dir=client.V1EmptyDirVolumeSource()),
                        client.V1Volume(name="tests", config_map=client.V1ConfigMapVolumeSource(name=configmap_name))
                    ],
                    init_containers=[
                        client.V1Container(
                            name="fetch-code",
                            image="alpine:3.18",
                            command=["/bin/sh", "-c", fetch_cmd],
                            env=[
                                client.V1EnvVar(
                                    name="GITLAB_TOKEN",
                                    value_from=client.V1EnvVarSource(
                                        secret_key_ref=client.V1SecretKeySelector(
                                            name="praxis-secrets",
                                            key="GITLAB_TOKEN"
                                        )
                                    )
                                )
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace")
                            ]
                        )
                    ],
                    containers=[
                        client.V1Container(
                            name="pytest",
                            image=evaluator_image,
                            command=["pytest", f"/tests/test_bug_{bug.id}.py"],
                            security_context=client.V1SecurityContext(
                                capabilities=client.V1Capabilities(drop=["ALL"]),
                                read_only_root_filesystem=True
                            ),
                            resources=client.V1ResourceRequirements(
                                limits={"cpu": "500m", "memory": "128Mi"}
                            ),
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace", read_only=True),
                                client.V1VolumeMount(name="tests", mount_path="/tests", read_only=True),
                                client.V1VolumeMount(name="tmp", mount_path="/tmp") # pytest needs tmp
                            ]
                        )
                    ]
                )
            )
        )
    )
    
    # Add an empty dir for /tmp so read_only_root_filesystem works
    job.spec.template.spec.volumes.append(
        client.V1Volume(name="tmp", empty_dir=client.V1EmptyDirVolumeSource())
    )

    try:
        batch_v1.create_namespaced_job(namespace=namespace, body=job)
    except ApiException as e:
        core_v1.delete_namespaced_config_map(name=configmap_name, namespace=namespace)
        return _fail_result(f"Failed to create Job: {e}", status="error", commit_sha=commit_sha)

    # Poll for completion
    timeout = 25
    elapsed = 0
    completed = False
    status_passed = False
    
    while elapsed < timeout:
        try:
            job_status = batch_v1.read_namespaced_job_status(name=job_id, namespace=namespace)
            if job_status.status.succeeded:
                completed = True
                status_passed = True
                break
            elif job_status.status.failed:
                completed = True
                status_passed = False
                break
        except ApiException:
            pass
        
        time.sleep(1)
        elapsed += 1

    # Fetch logs
    stdout_log = ""
    stderr_log = ""
    exit_code = 1 if not status_passed else 0
    status_str = "failed"
    
    try:
        # Find the pod associated with the job
        pods = core_v1.list_namespaced_pod(namespace=namespace, label_selector=f"job-name={job_id}")
        if pods.items:
            pod_name = pods.items[0].metadata.name
            
            # Fetch init container logs if it failed
            if not status_passed:
                try:
                    init_logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container="fetch-code")
                    if init_logs:
                        stderr_log += f"Init container logs:\n{init_logs}\n"
                except ApiException:
                    pass
            
            # Fetch main container logs
            try:
                logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, container="pytest")
                stdout_log += logs
            except ApiException:
                pass
    except ApiException:
        pass

    # Cleanup K8s resources
    try:
        batch_v1.delete_namespaced_job(
            name=job_id, 
            namespace=namespace, 
            propagation_policy="Background"
        )
        core_v1.delete_namespaced_config_map(name=configmap_name, namespace=namespace)
    except ApiException:
        pass

    if not completed:
        status_str = "timeout"
        exit_code = 124
        stderr_log += "\nJob timed out."
    elif status_passed:
        status_str = "passed"

    execution_time = time.time() - start_time
    
    return EvaluationResult(
        status=status_str,
        passed=status_passed,
        score=100 if status_passed else 0,
        exit_code=exit_code,
        stdout=stdout_log,
        stderr=stderr_log,
        execution_time=execution_time,
        commit_sha=commit_sha
    )

def _fail_result(msg: str, status: str = "failed", commit_sha: Optional[str] = None, exec_time: float = 0.0) -> EvaluationResult:
    return EvaluationResult(
        status=status,
        passed=False,
        score=0,
        exit_code=1,
        stdout="",
        stderr=msg,
        execution_time=exec_time,
        commit_sha=commit_sha
    )
