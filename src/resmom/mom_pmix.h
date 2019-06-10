
#include <pthread.h>
#include <pmix_server.h>

extern pmix_status_t
pbs_pmix_client_connected(
	const pmix_proc_t *proc,
	void *server_object,
	pmix_op_cbfunc_t cbfunc,
	void *cbdata);

extern pmix_status_t
pbs_pmix_client_finalized(
	const pmix_proc_t *proc,
	void *server_object,
	pmix_op_cbfunc_t cbfunc,
	void *cbdata);

extern pmix_status_t
pbs_pmix_fence_nb(
	const pmix_proc_t proc[],
	size_t procs,
	const pmix_info_t info[],
	size_t ninfo,
	char *data,
	size_t ndata,
	pmix_modex_cbfunc_t cbfunc,
	void *cbdata);

extern pmix_status_t
pbs_pmix_spawn(
	const pmix_proc_t *proc,
	const pmix_info_t job_info[],
	size_t ninfo,
	const pmix_app_t apps[],
	size_t napps,
	pmix_spawn_cbfunc_t cbfunc,
	void *cbdata);

extern void
pbs_pmix_wait_cb(
	pmix_status_t,
        void *
);

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    volatile bool active;
    pmix_status_t status;
} pbs_pmix_lock_t;

#define PBS_PMIX_CONSTRUCT_LOCK(l)                     \
    do {                                            \
        pthread_mutex_init(&(l)->mutex, NULL);      \
        pthread_cond_init(&(l)->cond, NULL);        \
        (l)->active = true;                         \
        (l)->status = PMIX_SUCCESS;                 \
    } while(0)

#define PBS_PMIX_DESTRUCT_LOCK(l)              \
    do {                                    \
        pthread_mutex_destroy(&(l)->mutex); \
        pthread_cond_destroy(&(l)->cond);   \
    } while(0)

#define PBS_PMIX_WAIT_THREAD(lck)                                      \
    do {                                                            \
        pthread_mutex_lock(&(lck)->mutex);                          \
        while ((lck)->active) {                                     \
            pthread_cond_wait(&(lck)->cond, &(lck)->mutex);         \
        }                                                           \
        pthread_mutex_unlock(&(lck)->mutex);                        \
    } while(0)

#define PBS_PMIX_WAKEUP_THREAD(lck)                        \
    do {                                                \
        pthread_mutex_lock(&(lck)->mutex);              \
        (lck)->active = false;                          \
        pthread_cond_broadcast(&(lck)->cond);           \
        pthread_mutex_unlock(&(lck)->mutex);            \
    } while(0)

