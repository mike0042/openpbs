
#include <pbs_config.h>

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <errno.h>

#include "mom_pmix.h"
#include "list_link.h"
#include "work_task.h"
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
	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	log_close(0);
	return PMIX_OPERATION_SUCCEEDED;
}

pmix_status_t
pbs_pmix_client_finalized(
	const pmix_proc_t *proc,
	void *server_object,
	pmix_op_cbfunc_t cbfunc,
	void *cbdata)
{
	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	log_close(0);
	return PMIX_OPERATION_SUCCEEDED;
}

pmix_status_t
pbs_pmix_fence_nb(
	const pmix_proc_t proc[],
	size_t procs,
	const pmix_info_t info[],
	size_t ninfo,
	char *data,
	size_t ndata,
	pmix_modex_cbfunc_t cbfunc,
	void *cbdata)
{
	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	log_close(0);
	return PMIX_OPERATION_SUCCEEDED;
}

typedef struct {
	const pmix_proc_t *proc;
	const pmix_info_t *job_info;
	size_t ninfo;
	const pmix_app_t *apps;
	size_t napps;
	pmix_spawn_cbfunc_t cbfunc;
	void *cbdata;
} pbs_pmix_spawn_t;

/*
 * Called as a work task created by pbs_pmix_spawn.
 */
void
pbs_pmix_spawn_cb(struct work_task *wt)
{
	pbs_pmix_spawn_t *params;
	int i, j;
	char **pp;

	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	if (!wt) {
		log_err(-1, __func__, "missing work task");
		return;
	}
	params = (pbs_pmix_spawn_t *)wt->wt_parm1;
	if (!params) {
		log_err(-1, __func__, "missing spawn parameters");
		return;
	}
	sprintf(log_buffer, "PMIx namespace is %s",
		(char *)params->proc->nspace);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	sprintf(log_buffer, "PMIx rank is %u",
		(unsigned)params->proc->rank);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	for (i = 0; i < params->ninfo; i++) {
		sprintf(log_buffer, "PMIx info %d: %s = %s (flags 0x%x)", i,
			params->job_info[i].key,
			params->job_info[i].value,
			(unsigned)params->job_info[i].flags);
		log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
	}
	for (i = 0; i < params->napps; i++) {
		sprintf(log_buffer, "PMIx cmd %d: %s", i,
			params->apps[i].cmd);
		sprintf(log_buffer, "PMIx app %d: %s", i,
			params->apps[i].cmd);
		for (pp = params->apps[i].argv; pp && *pp; pp++) {
			strcat(log_buffer, " ");
			strcat(log_buffer, *pp);
		}
		log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
		sprintf(log_buffer, "PMIx env %d:", i);
		for (pp = params->apps[i].env; pp && *pp; pp++) {
			strcat(log_buffer, " ");
			strcat(log_buffer, *pp);
		}
		log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
		sprintf(log_buffer, "PMIx cwd %d: %s", i, params->apps[i].cwd);
		log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
		sprintf(log_buffer, "PMIx maxprocs %d: %d", i, params->apps[i].maxprocs);
		log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
		for (j = 0; j < params->apps[i].ninfo; j++) {
			sprintf(log_buffer, "PMIx app %d info %d: %s = %s (flags 0x%x)",
				i, j,
				params->apps[i].info[j].key,
				params->apps[i].info[j].value,
				params->apps[i].info[j].flags);
			log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);
		}
	}

	/* Call tm_spawn to perform the actual execution */
	params->cbfunc(PMIX_SUCCESS, (char *)params->proc->nspace, params->cbdata);
}

/*
 * Create a work task to handle the spawn and return quickly.
 */
pmix_status_t
pbs_pmix_spawn(
	const pmix_proc_t *proc, 
	const pmix_info_t job_info[],
	size_t ninfo,
	const pmix_app_t apps[],
	size_t napps, 
	pmix_spawn_cbfunc_t cbfunc,
	void *cbdata)
{
	struct work_task *wt = NULL;
	pbs_pmix_spawn_t *params;

	log_open(log_file, path_log);
	sprintf(log_buffer, "%s called", __func__);
	log_event(PBSEVENT_DEBUG, 0, LOG_DEBUG, __func__, log_buffer);

	params = malloc(sizeof(pbs_pmix_spawn_t));
	if (!params)
		return PMIX_ERR_NOMEM;
	params->proc = proc;
	params->job_info = job_info;
	params->ninfo = ninfo;
	params->apps = apps;
	params->napps = napps;
	params->cbfunc = cbfunc;
	params->cbdata = cbdata;
	wt = set_task(WORK_Immed, 0, (void *)pbs_pmix_spawn_cb, params);
	if (!wt)
		log_err(errno, __func__,
			"Unable to set task for pbs_pmix_spawn_cb");
	else
		wt->wt_parm1 = (void *)params;

	log_close(0);
	return PMIX_SUCCESS;
}

void
pbs_pmix_wait_cb(pmix_status_t pstat, void *cbdata)
{
	PBS_PMIX_WAKEUP_THREAD((pbs_pmix_lock_t *)cbdata);
}
