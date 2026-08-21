# HIOP SECURITY DOCUMENTATION

## Authentication Model

HIOP uses JWT (JSON Web Tokens) for authentication with the following characteristics:

- **Token Type**: Bearer tokens (Authorization: Bearer <token>)
- **Algorithm**: HS256 (HMAC SHA-256)
- **Issuer**: "hiop"
- **Expiration**: 60 minutes (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)
- **Claims**: sub (email), role, exp (expiration), iat (issued at), iss (issuer), jti (token ID)
- **Storage**: Client-side (localStorage/sessionStorage) - not in cookies

## CSRF Protection

**Status**: Not implemented by design

**Rationale**: HIOP uses JWT bearer tokens for authentication, which are stored client-side and sent in the Authorization header. CSRF protection is not required because:

1. **Bearer tokens are not automatically sent**: Browsers do not automatically include Authorization headers in cross-origin requests
2. **Stateless authentication**: JWT-based authentication is stateless and doesn't rely on cookies
3. **CORS configuration provides protection**: The CORS configuration restricts which origins can access the API

**Security Considerations**:
- Tokens must be stored securely (HttpOnly cookies could be used for XSS protection, but this would require CSRF protection)
- XSS protection is critical since tokens are stored in JavaScript-accessible storage
- Content Security Policy (CSP) should be implemented in the frontend

## Session Model

**Current**: Stateless JWT tokens with 60-minute expiration

**Limitations**:
- No server-side token revocation capability
- Tokens remain valid until expiration even after logout or account changes
- No refresh token rotation

**Future Enhancements** (blocked by database permissions):
- Server-side token revocation via revoked_tokens table
- Refresh token rotation
- Session invalidation on password change
- Session invalidation on role changes
- Session invalidation on account deactivation

## Token Revocation

**Current Status**: Not implemented (blocked by database permissions)

**Intended Design**:
- Revoke tokens by JTI (JWT ID) in revoked_tokens table
- Automatic cleanup of expired revoked tokens
- Revocation reasons: logout, password_change, role_change, account_deactivation

## Password Policy

**Requirements**:
- Minimum length: 10 characters
- Must include: uppercase, lowercase, and numeric characters
- Maximum length: 128 characters

**Password Change**:
- Requires current password verification
- Requires new password confirmation
- Strong password validation
- Audit logging

**Password Reset**:
- Admin-initiated password reset exists
- Self-service password reset not implemented
- No reset token mechanism (blocked by database permissions)

## Temporary Passwords

**Status**: Not implemented (blocked by database permissions)

**Intended Design**:
- must_change_password field in users table
- Enforce password change on first login
- Temporary password expiration
- Single-use where practical

## Administrator Protection

**Current Status**: Basic role-based access control

**Implemented**:
- Role-based permissions (admin, technician, viewer)
- Platform administrator role for system-wide access
- Generic authentication errors (no user enumeration)

**Future Enhancements**:
- Recent authentication requirement for sensitive actions
- Session invalidation after role changes
- Stronger password policy for administrators
- Audit logging for administrative actions

## Login Security

**Implemented**:
- Generic error messages ("Invalid email or password")
- Rate limiting (10 failed attempts per 5 minutes per IP)
- Failed login logging
- Successful login logging
- Last login timestamp tracking

**Limitations**:
- Rate limiting is process-local (not distributed)
- No account lockout mechanism
- No suspicious activity detection

## Security Headers

**Implemented**:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: camera=(), microphone=(), geolocation=()
- X-XSS-Protection: 1; mode=block
- Cache-Control: no-store for API endpoints
- Strict-Transport-Security: max-age=31536000; includeSubDomains; preload (HTTPS only)

## CORS Configuration

**Current**: Explicit origins list (localhost:5173, 127.0.0.1:5173)

**Settings**:
- allow_credentials: False
- allow_methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
- allow_headers: Authorization, Content-Type, X-Organization-ID, X-HIOP-Organization-ID, X-HIOP-Property-ID

**Production Requirement**: Configure specific production origins (not "*")

## Rate Limiting

**Current**: Process-local rate limiting using in-memory data structures

**Limitations**:
- Not distributed across multiple backend instances
- Lost on process restart
- Not persistent

**Documentation Requirement**: Current deployment is single-instance, so process-local rate limiting is documented as acceptable for current scale.

## Security Event Auditing

**Implemented**:
- LOGIN_SUCCESS
- LOGOUT
- USER_CREATED
- USER_UPDATED
- USER_DEACTIVATED
- USER_ACTIVATED
- USER_ROLE_CHANGED
- PASSWORD_CHANGED (newly added)

**Not Implemented**:
- LOGIN_FAILURE (only logged via security logger)
- PASSWORD_RESET_REQUESTED
- PASSWORD_RESET_COMPLETED
- SESSION_REVOKED
- ROLE_CHANGE (partial)
- PROPERTY_ACCESS_CHANGE
- ORGANIZATION_ACCESS_CHANGE
- PLATFORM_ADMIN_CREATED
- PLATFORM_ADMIN_REMOVED

## Secret Handling

**Implemented**:
- Password hashing with bcrypt
- No password logging
- No password exposure in API responses
- Integration credentials encrypted at rest (AD, SNMP, SMTP)

**Configuration**:
- SECRET_KEY for JWT signing
- HIOP_AD_SECRET_KEY for AD encryption
- HIOP_SNMP_SECRET_KEY for SNMP encryption
- HIOP_DISCOVERY_CREDENTIAL_KEY for discovery credentials

**Requirements**:
- Environment-specific configuration
- No hardcoded secrets in code
- Secret rotation process

## File/Upload Security

**Status**: Limited file upload security review needed

**Requirements**:
- Authentication for file uploads
- Authorization for file access
- Organization/property scoping
- File type validation
- Size limits
- Safe filenames
- No path traversal
- No executable uploads
- No cross-tenant file access

## Production Security Configuration

**Environment Variables**:
- SECRET_KEY: JWT signing key (environment-specific)
- ACCESS_TOKEN_EXPIRE_MINUTES: Token expiration
- CORS_ORIGINS: Allowed frontend origins
- ENVIRONMENT: development/testing/production
- Various secret keys for credential encryption

**Requirements**:
- Strong random SECRET_KEY in production
- Specific CORS origins for production
- HTTPS required in production
- Secure cookie settings if cookies are used

## Dependency Security

**Key Security Libraries**:
- passlib: Password hashing (bcrypt)
- PyJWT: JWT token handling
- python-jose: JWT encoding/decoding
- cryptography: Used by passlib

**Status**: Not reviewed in this phase (future enhancement)

## Security Testing

**Current Status**: Limited security testing

**Required Tests**:
- Authentication flow tests
- Authorization tests
- Rate limiting tests
- Security header tests
- CORS tests
- Secret leak detection
- Integration security tests

## Remaining Security Blockers

1. **Database Permissions**: Cannot add security schema changes
   - must_change_password field
   - revoked_tokens table
   - Session revocation capability

2. **Windows Environment**: Cannot execute pg_dump for backup testing
   - Blocks actual security validation
   - Environment configuration needed

3. **Frontend Security**: Content Security Policy not implemented
   - XSS protection gaps
   - Token storage security needs review

## Security Compliance Status

**Current Level**: Basic production security

**Achieved**:
- Strong password hashing
- Secure JWT implementation
- Rate limiting
- Generic authentication errors
- Security headers
- CORS configuration
- Basic audit logging
- Password change functionality

**Not Achieved** (blocked by permissions/environment):
- Session revocation
- Temporary password enforcement
- Enhanced audit logging
- Complete security testing
- Frontend security (CSP)

**Recommendation**: Current security level is appropriate for initial production deployment with trusted users. Enhanced security features require database schema changes and environment configuration.