using GPV.ProductTimeFlow.Domain;

namespace GPV.ProductTimeFlow.UnitTests.Domain;

public class OvertimeCalculatorTests
{
    private static readonly DateOnly Day = new(2026, 3, 10);

    [Fact]
    public void Normal_range_computes_hours_on_same_day()
    {
        var calc = OvertimeCalculator.Calculate(Day, new TimeOnly(18, 0), new TimeOnly(21, 30));

        Assert.Equal(3.5m, calc.Hours);
        Assert.False(calc.CrossesMidnight);
        Assert.Equal(new DateTime(2026, 3, 10, 18, 0, 0), calc.StartLocal);
        Assert.Equal(new DateTime(2026, 3, 10, 21, 30, 0), calc.EndLocal);
    }

    [Fact]
    public void Range_crossing_midnight_ends_next_day()
    {
        var calc = OvertimeCalculator.Calculate(Day, new TimeOnly(22, 0), new TimeOnly(1, 30));

        Assert.Equal(3.5m, calc.Hours);
        Assert.True(calc.CrossesMidnight);
        Assert.Equal(new DateTime(2026, 3, 10, 22, 0, 0), calc.StartLocal);
        Assert.Equal(new DateTime(2026, 3, 11, 1, 30, 0), calc.EndLocal);
    }

    [Fact]
    public void Crossing_midnight_at_month_end_rolls_to_next_month()
    {
        var calc = OvertimeCalculator.Calculate(new DateOnly(2026, 1, 31), new TimeOnly(23, 0), new TimeOnly(0, 45));

        Assert.True(calc.CrossesMidnight);
        Assert.Equal(1.75m, calc.Hours);
        Assert.Equal(new DateTime(2026, 2, 1, 0, 45, 0), calc.EndLocal);
    }

    [Fact]
    public void Equal_times_are_interpreted_as_24_hours_by_calculator_and_rejected_by_validation_layer()
    {
        // El calculador interpreta fin <= inicio como cruce de medianoche; RequestRules rechaza explícitamente horas iguales
        // (ver WorkflowServiceTests.Overtime_with_equal_start_and_end_is_rejected).
        var calc = OvertimeCalculator.Calculate(Day, new TimeOnly(9, 0), new TimeOnly(9, 0));

        Assert.True(calc.CrossesMidnight);
        Assert.Equal(24m, calc.Hours);
    }

    [Theory]
    [InlineData(9, 0, 0, 9, 20, 0, 0.33)]   // 0.3333 → 0.33
    [InlineData(9, 0, 0, 9, 10, 0, 0.17)]   // 0.1666 → 0.17
    [InlineData(9, 0, 0, 9, 40, 0, 0.67)]   // 0.6666 → 0.67
    [InlineData(9, 0, 0, 9, 0, 18, 0.01)]   // 0.005 exacto → AwayFromZero → 0.01
    [InlineData(17, 15, 0, 19, 0, 0, 1.75)]
    public void Hours_are_rounded_to_two_decimals_away_from_zero(int sh, int sm, int ss, int eh, int em, int es, double expected)
    {
        var calc = OvertimeCalculator.Calculate(Day, new TimeOnly(sh, sm, ss), new TimeOnly(eh, em, es));
        Assert.Equal((decimal)expected, calc.Hours);
    }

    [Fact]
    public void Overlaps_detects_intersection_but_not_touching_intervals()
    {
        var a1 = new DateTime(2026, 3, 10, 18, 0, 0);
        var a2 = new DateTime(2026, 3, 10, 20, 0, 0);

        Assert.True(OvertimeCalculator.Overlaps(a1, a2, a1.AddHours(1), a2.AddHours(1)));
        Assert.True(OvertimeCalculator.Overlaps(a1, a2, a1, a2));
        Assert.False(OvertimeCalculator.Overlaps(a1, a2, a2, a2.AddHours(1)));
        Assert.False(OvertimeCalculator.Overlaps(a1, a2, a1.AddHours(-2), a1));
    }
}
