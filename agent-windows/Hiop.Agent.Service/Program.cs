using Hiop.Agent.Core;
using Hiop.Agent.Service;

var configPath = AgentConfiguration.DefaultPath;
if (args.Length == 2 && args[0] == "--config")
{
    configPath = Path.GetFullPath(args[1]);
}

var configuration = AgentConfiguration.Load(configPath);
var dataDirectory = AgentConfiguration.DefaultDataDirectory;
Directory.CreateDirectory(dataDirectory);
var credentialStore = new AgentCredentialStore(dataDirectory);
var observationQueue = new AgentObservationQueue(dataDirectory);
var status = new AgentRuntimeStatus();

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddWindowsService(options => options.ServiceName = "HIOP Local Agent");
builder.Services.AddSingleton(configuration);
builder.Services.AddSingleton(credentialStore);
builder.Services.AddSingleton(observationQueue);
builder.Services.AddSingleton(status);
builder.Services.AddSingleton<AgentApiClient>();
builder.Services.AddHostedService<AgentWorker>();
builder.Services.AddHostedService<AgentControlWorker>();

await builder.Build().RunAsync();
