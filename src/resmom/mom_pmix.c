
#include <pbs_config.h>

#include <stdio.h>

#include "mom_pmix.h"
#include "log.h"

extern char *log_file;
extern char *path_log;

pmix_status_t
pbs_pmix_client_connected(
	const pmix_proc_t *proc,
	void *server_object,
	pmix_op_cbfunc_t cbfunc,
	void *cbdata)
{
#if 0
	FILE *fp;
	fp = fopen("/tmp/pmix.out", "w");
	fprintf(fp, "%s called\n", __func__);
	fclose(fp);
#else
	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	log_close(0);
#endif
	return PMIX_OPERATION_SUCCEEDED;
}

pmix_status_t
pbs_pmix_client_finalized(
	const pmix_proc_t *proc,
	void *server_object,
	pmix_op_cbfunc_t cbfunc,
	void *cbdata)
{
#if 0
	FILE *fp;
	fp = fopen("/tmp/pmix.out", "a");
	fprintf(fp, "%s called\n", __func__);
	fclose(fp);
#else
	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	log_close(0);
#endif
	return PMIX_OPERATION_SUCCEEDED;
}

void
pbs_pmix_wait_cb(pmix_status_t pstat, void *cbdata)
{
	PBS_PMIX_WAKEUP_THREAD((pbs_pmix_lock_t *)cbdata);
}
