import os
import glob

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'PostgresActuationRepository' not in content:
        content = content.replace('PostgresReconciliationResultRepository', 'PostgresReconciliationResultRepository,\n    PostgresActuationRepository')
        content = content.replace('PostgresReconciliationResultRepository,\n)', 'PostgresReconciliationResultRepository,\n    PostgresActuationRepository\n)')

    if 'act_repo =' not in content:
        content = content.replace('recon_engine = V2ReconciliationEngine', 'act_repo = PostgresActuationRepository(session_maker)\n    recon_engine = V2ReconciliationEngine')
        content = content.replace('recon_engine = V2ReconciliationEngine', 'act_repo = PostgresActuationRepository(session_maker)\n        recon_engine = V2ReconciliationEngine') # indentation variations

    if 'actuation_repo=' not in content:
        content = content.replace('recon_result_repo=recon_repo,\n', 'recon_result_repo=recon_repo,\n        actuation_repo=act_repo,\n')

    with open(filepath, 'w') as f:
        f.write(content)

files = [
    'scripts/run_v2_e2e_loop.py',
    'scripts/worker_main.py',
    'tests/integration/test_deployment_crash_convergence.py',
    'tests/integration/test_architecture_resilience.py',
    'tests/integration/test_failure_scenarios.py',
    'tests/integration/test_end_to_end_vertical_slice.py',
    'tests/integration/test_end_to_end_ollama.py'
]

for f in files:
    patch_file(f)
    print(f"Patched {f}")
