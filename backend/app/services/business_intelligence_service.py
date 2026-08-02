"""Pure deterministic BI calculations. No dynamic code, ML, or recommendations."""
from decimal import Decimal, ROUND_HALF_UP

OPS={"sum":lambda xs:sum(xs,Decimal(0)),"average":lambda xs:sum(xs,Decimal(0))/Decimal(len(xs)) if xs else Decimal(0),"minimum":lambda xs:min(xs) if xs else Decimal(0),"maximum":lambda xs:max(xs) if xs else Decimal(0),"ratio":lambda xs:(xs[0]/xs[1]*100) if len(xs)>=2 and xs[1] else Decimal(0),"difference":lambda xs:xs[0]-xs[1] if len(xs)>=2 else Decimal(0)}
def quantize(value):return Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
def calculate_formula(operation,values):
    if operation not in OPS:raise ValueError("Unsupported KPI operation")
    return quantize(OPS[operation]([Decimal(str(value)) for value in values]))
def rolling_average(values,window):
    if window<1:raise ValueError("Window must be positive")
    data=[Decimal(str(x)) for x in values];return [quantize(sum(data[max(0,i-window+1):i+1],Decimal(0))/Decimal(len(data[max(0,i-window+1):i+1]))) for i in range(len(data))]
def growth_percentage(current,previous):return quantize((Decimal(str(current))-Decimal(str(previous)))/abs(Decimal(str(previous)))*100) if previous else Decimal(0)
def variance(actual,target):return {"absolute":quantize(Decimal(str(actual))-Decimal(str(target))),"percentage":growth_percentage(actual,target)}
def linear_forecast(values,periods):
    data=[Decimal(str(x)) for x in values]
    if not data or periods<1:return []
    n=Decimal(len(data));xs=[Decimal(i) for i in range(len(data))];mean_x=sum(xs)/n;mean_y=sum(data)/n;den=sum((x-mean_x)**2 for x in xs);slope=sum((xs[i]-mean_x)*(data[i]-mean_y) for i in range(len(data)))/den if den else Decimal(0);intercept=mean_y-slope*mean_x
    return [quantize(intercept+slope*Decimal(len(data)+i)) for i in range(periods)]
def trend(values):
    if len(values)<2:return {"direction":"stable","change_percent":Decimal(0)}
    change=growth_percentage(values[-1],values[0]);return {"direction":"increasing" if change>0 else "decreasing" if change<0 else "stable","change_percent":change}
