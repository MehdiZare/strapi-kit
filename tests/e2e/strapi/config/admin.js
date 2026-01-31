module.exports = ({ env }) => ({
  auth: {
    secret: env('ADMIN_JWT_SECRET', 'e2e-admin-jwt-secret-for-testing'),
  },
  apiToken: {
    salt: env('API_TOKEN_SALT', 'e2e-api-token-salt-for-testing'),
  },
  transfer: {
    token: {
      salt: env('TRANSFER_TOKEN_SALT', 'e2e-transfer-token-salt-for-testing'),
    },
  },
  flags: {
    nps: env.bool('FLAG_NPS', false),
    promoteEE: env.bool('FLAG_PROMOTE_EE', false),
  },
});
