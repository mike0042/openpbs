/*
 * Copyright (C) 1994-2020 Altair Engineering, Inc.
 * For more information, contact Altair at www.altair.com.
 *
 * This file is part of both the OpenPBS software ("OpenPBS")
 * and the PBS Professional ("PBS Pro") software.
 *
 * Open Source License Information:
 *
 * OpenPBS is free software. You can redistribute it and/or modify it under
 * the terms of the GNU Affero General Public License as published by the
 * Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version.
 *
 * OpenPBS is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
 * License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * Commercial License Information:
 *
 * PBS Pro is commercially licensed software that shares a common core with
 * the OpenPBS software.  For a copy of the commercial license terms and
 * conditions, go to: (http://www.pbspro.com/agreement.html) or contact the
 * Altair Legal Department.
 *
 * Altair's dual-license business model allows companies, individuals, and
 * organizations to create proprietary derivative works of OpenPBS and
 * distribute them - whether embedded or bundled with other software -
 * under a commercial license agreement.
 *
 * Use of Altair's trademarks, including but not limited to "PBS™",
 * "OpenPBS®", "PBS Professional®", and "PBS Pro™" and Altair's logos is
 * subject to Altair's trademark licensing policies.
 */



/**
 * @file	enc_JobCred.c
 * @brief
 * encode_DIS_JobCred() - encode a Job Credential Batch Request
 *
 * @par Data items are:
 * 			unsigned int	Credential type
 *			string		the credential (octet array)
 */

#include <pbs_config.h>   /* the master config generated by configure */

#include "libpbs.h"
#include "pbs_error.h"
#include "dis.h"

/**
 * @brief
 *	-encode a Job Credential Batch Request
 *
 * @par	Data items are:\n
 *		char		job id
 *		char		cred id (e.g principal)
 *		int	credential type
 *		counted string	the message
 *		long		credential validity
 *
 * @param[in] sock - socket descriptor
 * @param[in] jobid - job id
 * @param[in] owner - cred id (e.g. principal)
 * @param[in] type - cred type
 * @param[in] data - credential
 * @param[in] size - length of credential
 * @param[in] long - credential validity
 *
 * @return	int
 * @retval      0 for success
 * @retval      non-zero otherwise
 */

int
encode_DIS_Cred(int sock, char *jobid, char *credid, int type, char *data, size_t size, long validity)
{
	int   rc;

	if ((rc = diswst(sock, jobid) != 0) ||
		(rc = diswst(sock, credid) != 0) ||
		(rc = diswui(sock, type) != 0) ||
		(rc = diswcs(sock, data, size) != 0) ||
		(rc = diswul(sock, validity) != 0))
			return rc;

	return rc;
}
