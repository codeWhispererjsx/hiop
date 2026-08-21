const API_URL=import.meta.env.VITE_API_URL??"/api/v1";
export type PublicBillingPlan={id:string;code:string;name:string;description:string;audience:string|null;monthly_price:string|null;yearly_price:string|null;currency:string;trial_days:number;features:string[];limits:Record<string,number>;checkout_available:boolean};
export type OnboardingPayload={plan_code:string;organization_name:string;organization_code:string;contact_email:string;country:string;timezone:string;phone?:string;description?:string;property_name:string;property_code:string;property_city:string;admin_username:string;admin_email:string;admin_password:string};
export type OnboardingResult={access_token:string;organization:{id:string;name:string;code:string};property:{id:string;name:string;code:string};administrator:{id:string;username:string;email:string;role:"admin"};subscription:{id:string;status:string;trial_end:string|null}};
type ValidationIssue={loc?:Array<string|number>;msg?:string;type?:string};
const fieldMessages:Record<string,string>={
 admin_username:"Username can only contain letters, numbers, periods, underscores, and hyphens. Spaces are not allowed.",
 admin_password:"Password must be 12–128 characters and include uppercase, lowercase, and a number.",
 admin_email:"Enter a valid administrator email address.",
 contact_email:"Enter a valid organization contact email address.",
 organization_code:"Enter an organization code using at least two letters or numbers.",
 property_code:"Enter a property code using at least two letters or numbers.",
};
function safeValidationMessage(detail:ValidationIssue[]):string{
 const messages=detail.map(issue=>{
  const field=String(issue.loc?.at(-1)??"");
  if(fieldMessages[field])return fieldMessages[field];
  const message=issue.msg??"";
  if(/string should match pattern/i.test(message))return "One of the entered values contains unsupported characters.";
  return message.replace(/^Value error,\s*/i,"");
 }).filter(Boolean);
 return [...new Set(messages)].join(" ")||"Please review the highlighted information and try again.";
}
export async function registerCustomer(payload:OnboardingPayload):Promise<OnboardingResult>{
 const response=await fetch(`${API_URL}/public/onboarding/register`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
 if(!response.ok){let message="Unable to complete organization setup.";try{const body=await response.json() as {detail?:string|ValidationIssue[]};message=typeof body.detail==="string"?body.detail:Array.isArray(body.detail)?safeValidationMessage(body.detail):message}catch{/* keep safe message */}throw new Error(message)}
 return response.json();
}
export async function getPublicPlans():Promise<PublicBillingPlan[]>{const response=await fetch(`${API_URL}/billing/public/plans`);if(!response.ok)throw new Error("Unable to load current plans.");return response.json()}
