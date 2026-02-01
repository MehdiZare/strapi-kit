'use strict';

// Strapi bootstrap for E2E testing
// Creates admin user and API token on first startup

module.exports = {
  async bootstrap({ strapi }) {
    await createAdminUser(strapi);
    await createApiToken(strapi);
    await logContentTypes(strapi);
  },
};

async function logContentTypes(strapi) {
  const apiContentTypes = Object.keys(strapi.contentTypes).filter(
    (key) => key.startsWith('api::')
  );
  console.log('[E2E] Registered API content types:', apiContentTypes);
}

async function createAdminUser(strapi) {
  const adminEmail = 'admin@e2e-test.local';

  try {
    const existingAdmin = await strapi.query('admin::user').findOne({
      where: { email: adminEmail },
    });

    if (existingAdmin) {
      console.log('[E2E] Admin user already exists');
      return;
    }

    const superAdminRole = await strapi.query('admin::role').findOne({
      where: { code: 'strapi-super-admin' },
    });

    if (!superAdminRole) {
      console.error('[E2E] Super admin role not found');
      return;
    }

    const hashedPassword = await strapi.service('admin::auth').hashPassword('Admin123!');

    await strapi.query('admin::user').create({
      data: {
        email: adminEmail,
        password: hashedPassword,
        firstname: 'E2E',
        lastname: 'Admin',
        isActive: true,
        roles: [superAdminRole.id],
      },
    });

    console.log('[E2E] Created admin user:', adminEmail);
  } catch (error) {
    console.error('[E2E] Failed to create admin user:', error?.message || error);
  }
}

async function createApiToken(strapi) {
  const tokenName = 'e2e-test-token';

  try {
    // Check for existing token
    const existingTokens = await strapi.query('admin::api-token').findMany({
      where: { name: tokenName },
    });

    if (existingTokens.length > 0) {
      // Token exists but we can't retrieve the accessKey (it's hashed)
      // Delete and recreate to ensure we have a fresh token we can log
      console.log(`[E2E] Removing existing API token "${tokenName}" to recreate...`);
      for (const token of existingTokens) {
        await strapi.query('admin::api-token').delete({ where: { id: token.id } });
      }
    }

    // Create new token
    const tokenService = strapi.service('admin::api-token');

    const token = await tokenService.create({
      name: tokenName,
      description: 'API token for strapi-kit E2E tests',
      type: 'full-access',
      lifespan: null,
    });

    console.log('[E2E] ============================================');
    console.log('[E2E] API TOKEN CREATED FOR E2E TESTS');
    console.log(`[E2E] Token: ${token.accessKey}`);
    console.log('[E2E] ============================================');
  } catch (error) {
    console.error('[E2E] Failed to create API token:', error?.message || error);
  }
}
