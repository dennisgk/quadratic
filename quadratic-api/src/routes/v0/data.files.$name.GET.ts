import type { Request, Response } from 'express';
import path from "path";
import { z } from 'zod';
import { API_FILES_DIR } from '../../env-vars';
import { userMiddleware } from '../../middleware/user';
import { validateAccessToken } from '../../middleware/validateAccessToken';
import { validateRequestSchema } from '../../middleware/validateRequestSchema';
import type { RequestWithUser } from '../../types/Request';

export default [
  validateRequestSchema(
    z.object({
      params: z.object({
        name: z.string(),
      }),
    })
  ),
  validateAccessToken,
  userMiddleware,
  handler,
];

async function handler(req: Request, res: Response) {
  const {
    params: { name },
  } = req as RequestWithUser;

  return res.sendFile(path.join(API_FILES_DIR, name), (err) => {
    if (err) {
      console.error(err);
      return res.status(404).send("File not found");
    }
  });
}
